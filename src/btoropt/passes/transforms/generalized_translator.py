# =====================================================================
# Nidhi Lawange
#
# Description:
# Generalized BTOR2-to-CIRCT translator that parses a BTOR2 program, constructs
# hardware module interfaces, translates BTOR2 instructions into CIRCT IR using
# the HW and Comb dialects, and generates an MLIR representation of the input btor2 program.
# The translator is designed to be easily adaptable and scalable to support additional btor operations and sequential hardware constructs.
# ========================================================================
import circt
from circt.ir import (
    Context, 
    Location, 
    Module, 
    InsertionPoint, 
    IntegerType)

from btoropt.parser import parse
from circt.dialects import hw, comb
# from circt.ir import *

# print(Location)
# print(Context)
# print(help(Location))
class Btor2CirctTranslator:
    def __init__(self, program):
        self.program = program

        # dictionary data structure for mapping btor line id to circt ssa value
        self.line_value_dict = {}

        # dictionary for mapping the btor line id reference (to a sort [type]) to an actual circt operation type
        self.line_type_dict = {}

    def construct_type_dict(self):
        for instruction in self.program:
            if instruction.inst == "sort":
                bit_width = instruction.width
                circt_type = IntegerType.get_signless(bit_width)
                self.line_type_dict[instruction.lid] = circt_type
    
    # constructing input ports in the Module interface: what inputs does this hardware module have?
    def construct_input_ports(self):
        input_ports_gen_list = []
        for instruction in self.program:
            if instruction.inst == "input":
                input_type = self.line_type_dict[instruction.sid]
                input_ports_gen_list.append((instruction.name, input_type))
        return input_ports_gen_list

    # constructing output ports in the Module interface: what outputs does this hardware module have?
    def construct_output_ports(self):
        output_ports_gen_list = []

        for instruction in self.program:
            if instruction.inst == "output":

                # instruction itself that's driving the output
                source_instruction = instruction.operands[0]

                # first operand of every instruction producing some value is its Sort (type)
                sort_instruction = source_instruction.operands[0]

                output_type = self.line_type_dict[sort_instruction.lid]

                output_ports_gen_list.append((instruction.name, output_type))

        return output_ports_gen_list
    
    # map input PORTS to their SSA values
    def map_input_ports_values(self, block):
        # block arguments correspond to the hardware module input ports
        # (e.g., block.arguments[0] -> %a, block.arguments[1] -> %b)
        block_arg_index = 0

        for instruction in self.program:
            # process every BTOR2 input instruction
            if instruction.inst == "input":

                # obtain the corresponding CIRCT SSA value from the module input ports
                input_value = block.arguments[block_arg_index]

                # map the BTOR2 input line ID to its CIRCT SSA value
                # Example: line 2 -> %a, line 3 -> %b
                self.line_value_dict[instruction.lid] = input_value

                # move to the next hardware module input port
                block_arg_index += 1

    
    # mapping operation results to SSA values
    #def translate_add_instruction(self):
        #for instruction in self.program:
            #if instruction.inst == "add":

                # operands[1] and operands[2] correspond to the left and right input instructions of btor2 add operation
                #left_instruction = instruction.operands[1]
                #right_instruction = instruction.operands[2]

                # obtain the CIRCT SSA values that were previously generated for the left and right btor2 operands
                #left_val = self.line_value_dict[left_instruction.lid]
                #right_val = self.line_value_dict[right_instruction.lid]

                # create the corresponding CIRCT comb.add operation
                #add_op = comb.AddOp([left_val, right_val])

                # store resulting CIRCT SSA value using the BTOR2 line ID so that future btor2 instructions can reference it
                #self.line_value_dict[instruction.lid] = add_op.result

    # replace translate_add_instruction() with the following method which now utilizes the new generalized translate_binary_operation() function
    def translate_any_binary_instruction(self):
        for instruction in self.program:

            if instruction.inst == "add":
                self.translate_binary_operation(instruction,comb.AddOp)

            elif instruction.inst == "sub":
                self.translate_binary_operation(instruction,comb.SubOp)

            elif instruction.inst == "and":
                self.translate_binary_operation(instruction,comb.AndOp)

            elif instruction.inst == "or":
                self.translate_binary_operation(instruction,comb.OrOp)

            elif instruction.inst == "xor":
                self.translate_binary_operation(instruction,comb.XorOp)
    
    def translate_binary_operation(self, instruction, circt_operation):
        # operands[1] and operands[2] are the left and right btor2 operands
        left_instruction = instruction.operands[1]
        right_instruction = instruction.operands[2]

        # retrieve the circt SSA values previously generated for both operands
        left_value = self.line_value_dict[left_instruction.lid]
        right_value = self.line_value_dict[right_instruction.lid]

        # create the corresponding CIRCT binary operation
        operation = circt_operation([left_value, right_value])

        # map this btor2 instruction's line ID to the newly generated SSA value
        self.line_value_dict[instruction.lid] = operation.result

    def translate_btor_program(self):
        
        with Context() as ctx, Location.unknown():
            # register all CIRCT dialects (hw, comb, seq, sv, ...) so that these operations can be created
            circt.register_dialects(ctx)
            
            # the type
            # Replace this: i8 = IntegerType.get_signless(8)
            # with this: using the construct_type_dict() function
            self.construct_type_dict()
            print("Type map:", self.line_type_dict)
            i8 = self.line_type_dict[1]
            
            input_ports_list = self.construct_input_ports()
            output_ports_list = self.construct_output_ports()
            module = Module.create()
            # new operations inserted into the module body
            with InsertionPoint(module.body):
                #create hardware module --> corresponds to hw.module @comb_adder()
                adder = hw.HWModuleOp(
                name="comb_adder",
                # replace [("a",i8), ("b",i8)] with input_ports_list returned from construct_input_ports()
                # replace [("c",i8)] with output_ports_list returned from construct_output_ports()
                input_ports=input_ports_list,
                output_ports=output_ports_list
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
                # replace this: a = block.arguments[0] # input "a", b = block.arguments[1] # input "b" with:
                self.map_input_ports_values(block)

                # circt version expects the operands as a list rather than 2 separate arguments (self, list = [input,output])
                # replace this: sum_op = comb.AddOp([a,b]), sum_val = # sum_op.result with:
                #self.translate_add_instruction()
                self.translate_any_instruction()

                # create hardware output operation --> hw.output %0 - %0 is sum_val
                # replace this:hw.OutputOp([self.line_value_dict[5]]) with this:
                output_values = self.map_output_values()
                hw.OutputOp(output_values)

            # printing mlir:)
            return(module)
def main():
    with open("comb_adder_extrainput.btor2", "r") as file:
        program = parse(file.readlines())

    #for instruction in program:
     #   if instruction.inst == "input":
      #      print(vars(instruction))
    
    #for instruction in program:
     #   if instruction.inst == "output":
      #      print(vars(instruction))
            
    translator = Btor2CirctTranslator(program)
    module = translator.translate_btor_program()

    print(module)


if __name__ == "__main__":
    main()