# ========================================================================# Nidhi Lawange
#
# Description:
# Demonstrates a simple BTOR2-inspired combinational adder in CIRCT Python.
# Creates an 8-bit hardware module with two inputs and one output, generates
# a combinational addition using the HW and Comb dialects, and prints the
# resulting CIRCT MLIR representation. This serves as the foundation for the
# generalized BTOR2-to-CIRCT translator.
# ========================================================================

import circt
from circt.ir import Context, Location, Module, InsertionPoint, IntegerType
from circt.dialects import hw, comb
# from circt.ir import *

# print(Location)
# print(Context)
# print(help(Location))

with Context() as ctx, Location.unknown():
    # register all CIRCT dialects (hw, comb, seq, sv, ...) so that these operations can be created
    circt.register_dialects(ctx)
    # the type
    i8 = IntegerType.get_signless(8)
    module = Module.create()
    # new operations inserted into the module body
    with InsertionPoint(module.body):
        # create hardware module --> corresponds to hw.module @comb_adder()
        adder = hw.HWModuleOp(
        name="comb_adder",
        input_ports=[("a", i8), ("b", i8)],
        output_ports=[("c", i8)]
        )
        # print(type(adder))
        # print(dir(adder))
        # help(adder) --> add_entry_block()

    # HWModuleOp
    #     |
    # body (Region)
    #     |
    # Block
    #
    # Since the Region initially contains no blocks, we must explicitly create one.
    block = adder.add_entry_block()

    with InsertionPoint(block):
        # block arguments => correspond to hardware module input ports
        a = block.arguments[0] # input "a"
        b = block.arguments[1] # input "b"

        # print(a)
        # print(b)
        # help(InsertionPoint)
        # dir(block)
        # help(block)
        #help(comb.AddOp)
        # help(sum_op)
        # dir(sum_op)
        
        # circt version expects the operands as a list rather than 2 separate arguments (self, list = [input,output])
        sum_op = comb.AddOp([a,b])
        # .result = basically extracting the output wire connection of that adder ^
        sum_val = sum_op.result
        # create hardware output operation --> hw.output %0 - %0 is sum_val
        hw.OutputOp([sum_val])
    # printing mlir:)
    print(module)
