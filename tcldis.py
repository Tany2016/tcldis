from __future__ import print_function

import struct

import _tcldis
printbc = _tcldis.printbc
getbc = _tcldis.getbc

INSTRUCTIONS = _tcldis.inst_table()
JUMP_INSTRUCTIONS = (
    'jump1', 'jump4', 'jumpTrue1', 'jumpTrue4', 'jumpFalse1', 'jumpFalse4'
)

def _getop(optype):
    """
    Given a C struct descriptor, return a function which will take the necessary
    bytes off the front of a bytearray and return the python value.
    """
    def getop_lambda(bc):
        # The 'standard' sizes in the struct module match up to what Tcl expects
        numbytes = struct.calcsize(optype)
        opbytes = ''.join([chr(bc.pop(0)) for i in range(numbytes)])
        return struct.unpack(optype, opbytes)[0]
    return getop_lambda

# InstOperandType from tclCompile.h
OPERANDS = [
    ('NONE',  None), # Should never be present
    ('INT1',  _getop('>b')),
    ('INT4',  _getop('>i')),
    ('UINT1', _getop('>B')),
    ('UINT4', _getop('>I')),
    ('IDX4',  _getop('>i')),
    ('LVT1',  _getop('>B')),
    ('LVT4',  _getop('>I')),
    ('AUX4',  _getop('>I')),
]

# Tcl bytecode instruction
class Inst(object):
    def __init__(self, bytecode, loc, *args, **kwargs):
        super(Inst, self).__init__(*args, **kwargs)
        inst_type = INSTRUCTIONS[bytecode.pop(0)]
        self.name = inst_type['name']
        self.ops = []
        for opnum in inst_type['operands']:
            optype = OPERANDS[opnum]
            self.ops.append((optype[0], optype[1](bytecode)))
        self.loc = loc
        # Note that this doesn't get printed on str() so we only see
        # the value when it gets reduced to a BCJump class
        if self.name in JUMP_INSTRUCTIONS:
            self.targetloc = self.loc + self.ops[0][1]

    def __repr__(self):
        return '<%s: %s %s>' % (
            self.loc if self.loc is not None else '?',
            self.name,
            self.ops
        )

#################################################################
# My own representation of anything that can be used as a value #
#################################################################

# The below three represent my interpretation of the Tcl stack
class BCValue(object):
    def __init__(self, inst, value, *args, **kwargs):
        super(BCValue, self).__init__(*args, **kwargs)
        self.inst = inst
        self.value = value
    def __repr__(self): assert False
    def fmt(self): assert False

class BCLiteral(BCValue):
    def __init__(self, *args, **kwargs):
        super(BCLiteral, self).__init__(*args, **kwargs)
    def __repr__(self):
        return 'BCLiteral(%s)' % (repr(self.value),)
    def fmt(self):
        return self.value

class BCVarRef(BCValue):
    def __init__(self, *args, **kwargs):
        super(BCVarRef, self).__init__(*args, **kwargs)
        assert len(self.value) == 1
    def __repr__(self):
        return 'BCVarRef(%s)' % (repr(self.value),)
    def fmt(self):
        return '$' + self.value[0].fmt()

class BCArrayRef(BCValue):
    def __init__(self, *args, **kwargs):
        super(BCArrayRef, self).__init__(*args, **kwargs)
        assert len(self.value) == 2
    def __repr__(self):
        return 'BCArrayRef(%s)' % (repr(self.value),)
    def fmt(self):
        return '$' + self.value[0].fmt() + '(' + self.value[1].fmt() + ')'

class BCProcCall(BCValue):
    def __init__(self, *args, **kwargs):
        super(BCProcCall, self).__init__(*args, **kwargs)
    def __repr__(self):
        return 'BCProcCall(%s)' % (self.value,)
    def fmt(self):
        cmd = ' '.join([arg.fmt() for arg in self.value])
        cmd = '[' + cmd + ']'
        return cmd

####################################################################
# My own representation of anything that cannot be used as a value #
####################################################################

class BCNonValue(object):
    def __init__(self, inst, value, *args, **kwargs):
        super(BCNonValue, self).__init__(*args, **kwargs)
        self.inst = inst
        self.value = value
    def __repr__(self): assert False
    def fmt(self): assert False

# Represents ignored return values from proc calls
class BCIgnoredProcCall(BCNonValue):
    def __init__(self, *args, **kwargs):
        super(BCIgnoredProcCall, self).__init__(*args, **kwargs)
        assert len(self.value) == 1
        assert isinstance(self.value[0], BCProcCall)
    def __repr__(self):
        return 'BCIgnoredProcCall(%s)' % (self.value,)
    def fmt(self):
        return self.value[0].fmt()[1:-1]

class BCJump(BCNonValue):
    def __init__(self, on, *args, **kwargs):
        super(BCJump, self).__init__(*args, **kwargs)
        assert len(self.value) == 0 if on is None else 1
        self.on = on
        self.targetloc = self.inst.targetloc
    def __repr__(self):
        return 'BCJump(%s==%s)->%s' % (self.on, self.value, self.inst.targetloc)
    def fmt(self):
        #return 'JUMP%s(%s)' % (self.on, self.value[0].fmt())
        return str(self)

##############################
# Any basic block structures #
##############################

# Basic block, containing a linear flow of logic
class BBlock(object):
    def __init__(self, insts, loc, *args, **kwargs):
        super(BBlock, self).__init__(*args, **kwargs)
        self.insts = insts
        self.loc = loc
    def __repr__(self):
        return 'BBlock(at %s, %s insts)' % (self.loc, len(self.insts))
    def fmt(self):
        return '\n'.join([
            inst.fmt() if not isinstance(inst, Inst) else str(inst)
            for inst in self.insts
        ]) + '\n'

class BBFlow(object):
    def __init__(self, bblocks,  *args, **kwargs):
        super(BBFlow, self).__init__(*args, **kwargs)
        self.bblocks = bblocks
    def __repr__(self): assert False
    def fmt(self): assert False

class BBFlowIf(BBFlow):
    def __init__(self, condition, *args, **kwargs):
        super(BBFlowIf, self).__init__(*args, **kwargs)
        assert len(self.bblocks) == 1
        assert isinstance(condition, BCJump)
        self.condition = condition
    def __repr__(self):
        return 'BBFlowIf(%s)' % (self.bblocks,)
    def fmt(self):
        conditionstr = self.condition.value[0].fmt()
        if self.condition.on is True:
            conditionstr = '!' + conditionstr
        return (
            'if {%s} {\n' + self.bblocks[0].fmt() + '}'
        ) % (conditionstr,)

########################
# Functions start here #
########################

def getinsts(bytecode):
    """
    Given bytecode in a bytearray, return a list of Inst objects.
    """
    bytecode = bytecode[:]
    insts = []
    pc = 0
    while len(bytecode) > 0:
        num_bytes = INSTRUCTIONS[bytecode[0]]['num_bytes']
        insts.append(Inst(bytecode[:num_bytes], pc))
        pc += num_bytes
        bytecode = bytecode[num_bytes:]
    return insts

def _bblock_create(insts):
    """
    Given a list of Inst objects, split them up into basic blocks.
    """
    # Identify the beginnings and ends of all basic blocks
    starts = set()
    ends = set()
    newstart = True
    for i, inst in enumerate(insts):
        if newstart:
            starts.add(inst.loc)
            newstart = False
        if inst.name in JUMP_INSTRUCTIONS:
            ends.add(inst.loc)
            starts.add(inst.targetloc)
            newstart = True
            # inst before target inst is end of a bblock
            # search through instructions for instruction before the target
            if inst.targetloc != 0:
                instbeforeidx = 0
                while True:
                    if insts[instbeforeidx+1].loc == inst.targetloc: break
                    instbeforeidx += 1
                instbefore = insts[instbeforeidx]
                ends.add(instbefore.loc)
    ends.add(insts[-1].loc)
    # Create the basic blocks
    assert len(starts) == len(ends)
    bblocks = []
    bblocks_insts = insts[:]
    for start, end in zip(sorted(list(starts)), sorted(list(ends))):
        bbinsts = []
        assert bblocks_insts[0].loc == start
        while bblocks_insts[0].loc < end:
            bbinsts.append(bblocks_insts.pop(0))
        assert bblocks_insts[0].loc == end
        bbinsts.append(bblocks_insts.pop(0))
        bblocks.append(BBlock(bbinsts, bbinsts[0].loc))
    # Jump fixup
    for inst in insts:
        if inst.name not in JUMP_INSTRUCTIONS:
            continue
        for bblock in bblocks:
            if inst.targetloc == bblock.loc:
                inst.targetloc = bblock
                break
        else:
            assert False
    return bblocks

def _inst_reductions():
    """
    Define how each instruction is reduced to one of my higher level
    representations.
    """
    def N(n): return lambda _: n
    firstop = lambda inst: inst.ops[0][1]
    inst_reductions = {
        'invokeStk1': {'nargs': firstop, 'redfn': BCProcCall},
        'invokeStk4': {'nargs': firstop, 'redfn': BCProcCall},
        'jump1': {'nargs': N(0), 'redfn': lambda i, v: BCJump(None, i, v)},
        'jumpFalse1': {'nargs': N(1), 'redfn': lambda i, v: BCJump(False, i, v)},
        'jumpTrue1': {'nargs': N(1), 'redfn': lambda i, v: BCJump(True, i, v)},
        'loadArrayStk': {'nargs': N(2), 'redfn': BCArrayRef},
        'loadStk': {'nargs': N(1), 'redfn': BCVarRef},
        'nop': {'nargs': N(0), 'redfn': lambda _1, _2: []},
        'pop': {'nargs': N(1), 'redfn': BCIgnoredProcCall, 'checktype': BCProcCall},
        'storeStk': {'nargs': N(2), 'redfn': lambda inst, kv: BCProcCall(inst, [BCLiteral(None, 'set'), kv[0], kv[1]])},
    }
    return inst_reductions

INST_REDUCTIONS = _inst_reductions()

def _bblock_reduce(bblock, literals):
    """
    For the given basic block, attempt to reduce all instructions to my higher
    level representations.
    """
    loopchange = True
    while loopchange:
        loopchange = False
        for i, inst in enumerate(bblock.insts[:]):
            if not isinstance(inst, Inst): continue
            if inst.name in ('push1', 'push4'):
                bblock.insts[i] = BCLiteral(inst, literals[inst.ops[0][1]])
                loopchange = True
                break

            elif inst.name in INST_REDUCTIONS:
                IRED = INST_REDUCTIONS[inst.name]
                nargs = IRED['nargs'](inst)
                checktype = IRED.get('checktype', BCValue)
                redfn = IRED['redfn']

                arglist = bblock.insts[i-nargs:i]
                if len(arglist) != nargs: continue
                if not all([isinstance(arg, checktype) for arg in arglist]):
                    continue
                newinsts = redfn(inst, arglist)
                if type(newinsts) is not list:
                    newinsts = [newinsts]
                bblock.insts[i-nargs:i+1] = newinsts
                loopchange = True
                break

def _get_jump(bblock):
    jump = bblock.insts[-1]
    return jump if isinstance(jump, BCJump) else None

def _bblock_flow(bblocks):
    # Recognise a basic if
    loopchange = True
    while loopchange:
        loopchange = False
        for i, bblock in enumerate(bblocks):
            jump = _get_jump(bblock)
            if jump is None or jump.on is None:
                continue
            if len(bblocks[i:]) < 3:
                continue
            if _get_jump(bblocks[i+1]) is not None:
                continue
            if jump.targetloc is not bblocks[i+2]:
                continue
            targets = [
                (lambda jump: jump and jump.targetloc)(_get_jump(src_bblock))
                for src_bblock in bblocks
            ]
            if bblocks[i+1] in targets:
                continue
            if targets.count(bblocks[i+2]) > 1:
                continue
            initialcondition = bblocks[i].insts.pop()
            bblocks[i].insts.append(BBFlowIf(initialcondition, bblocks[i+1:i+2]))
            bblocks[i].insts.extend(bblocks[i+2].insts)
            bblocks[i+1:i+3] = []
            loopchange = True
            break

def decompile(tcl_code):
    """
    Given some tcl code, compile it to bytecode then attempt to decompile it.
    """
    bytecode, literals = getbc(tcl_code)
    insts = getinsts(bytecode)
    bblocks = _bblock_create(insts)
    # Reduce bblock logic
    [_bblock_reduce(bblock, literals) for bblock in bblocks]
    _bblock_flow(bblocks)
    outstr = ''
    for bblock in bblocks:
        outstr += bblock.fmt()
    return outstr
