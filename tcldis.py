from __future__ import print_function

import struct

import _tcldis
printbc = _tcldis.printbc
getbc = _tcldis.getbc

INSTRUCTIONS = _tcldis.inst_table()

def getop(numbytes, optype):
    def getop_lambda(bc):
        opbytes = ''.join([chr(bc.pop(0)) for i in range(numbytes)])
        return struct.unpack(optype, opbytes)[0]
    return getop_lambda

# InstOperandType from tclCompile.h
OPERANDS = [
    ('NONE',  None), # Should never be present
    ('INT1',  getop(1,'>b')),
    ('INT4',  getop(4,'>i')),
    ('UINT1', getop(1,'>B')),
    ('UINT4', getop(4,'>I')),
    ('IDX4',  getop(4,'>i')),
    ('LVT1',  getop(1,'>B')),
    ('LVT4',  getop(4,'>I')),
    ('AUX4',  getop(4,'>I')),
]

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

    def __repr__(self):
        return '<%s: %s %s>' % (
            self.loc if self.loc is not None else '?',
            self.name,
            self.ops
        )

class BBlock(object):
    def __init__(self, *args, **kwargs):
        super(BBlock, self).__init__(*args, **kwargs)
        self.insts = []
    def __repr__(self):
        return 'BBlock(%s-%s)' % (self.insts[0].loc, self.insts[-1].loc)

def getinsts(bytecode):
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
    # Identify the beginnings and ends of all basic blocks
    starts = set()
    ends = set()
    jumps = ('jump1', 'jump4', 'jumpTrue1', 'jumpTrue4', 'jumpFalse1', 'jumpFalse4')
    newstart = True
    for i, inst in enumerate(insts):
        if newstart:
            starts.add(inst.loc)
            newstart = False
        if inst.name in jumps:
            ends.add(inst.loc)
            targetloc = inst.loc + inst.ops[0][1]
            starts.add(targetloc)
            newstart = True
            # inst before target inst is end of a bblock
            # search through instructions for instruction before the target
            if targetloc != 0:
                instbeforeidx = 0
                while True:
                    if insts[instbeforeidx+1].loc == targetloc: break
                    instbeforeidx += 1
                instbefore = insts[instbeforeidx]
                ends.add(instbefore.loc)
    ends.add(insts[-1].loc)
    # Create the basic blocks
    assert len(starts) == len(ends)
    bblocks = []
    bblock_insts = insts[:]
    for start, end in zip(sorted(list(starts)), sorted(list(ends))):
        bblock = BBlock()
        assert bblock_insts[0].loc == start
        while bblock_insts[0].loc < end:
            bblock.insts.append(bblock_insts.pop(0))
        assert bblock_insts[0].loc == end
        bblock.insts.append(bblock_insts.pop(0))
        bblocks.append(bblock)
    return bblocks

def _bblock_literals(bblock, tclvars):
    for inst in bblock.insts:
        if inst.name in ('push1', 'push4'):
            inst.ops = [tclvars[op_val] for op_type, op_val in inst.ops]

def _bblock_reduce(bblock):
    return False

def decompile(tcl_code):
    bytecode, tclvars = getbc(tcl_code)
    insts = getinsts(bytecode)
    bblocks = _bblock_create(insts)
    # Insert literals into instructions
    [_bblock_literals(bblock, tclvars) for bblock in bblocks]
    # Reduce bblock logic
    while any([_bblock_reduce(bblock) for bblock in bblocks]):
        pass
    return [bblock.insts for bblock in bblocks]
