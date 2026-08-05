# =====================================================================
# Nidhi Lawange
#
# Description:
# Generalized BTOR2-to-CIRCT translation pass that receives an already-parsed BTOR2 program from the btor2-opt pass infrastructure, constructs hardware module interfaces, translates BTOR2 instructions into CIRCT IR using the HW and Comb dialects, and generates an MLIR representation of the input BTOR2 program. The translator is designed to be easily adaptable and scalable to support additional BTOR2 operations and sequential hardware constructs.
#=======================================================================

import circt
import inspect

from circt.ir import (
    Context,
    Location,
    Module,
    InsertionPoint,
    IntegerType,
    Attribute
)

from circt.dialects import hw, comb

# Import the existing btor2-opt pass interface.
from ..genericpass import Pass
from ...program import Instruction, Sort, Input, Output, Add, Sub, And, Or, Xor, Const, Constd, Consth, Zero, One, Ones, Not, Inc, Dec, Neg, Redor, Redand, Redxor, Eq, Neq, Ugt, Ugte, Ult, Ulte, Sgt, Sgte, Slt, Slte, Ite, Slice, Concat, Uext, Sext


# The generalized translator now inherits from Pass so it can be invoked
# through the existing btor2-opt pass infrastructure.
class Btor2CirctTranslator(Pass):

    def __init__(self):
        # Name used to identify this pass in the pass infrastructure.
        super().__init__("generalized-translator")

        # The parsed BTOR2 program is supplied by the pass infrastructure
        # when run() is called.
        self.program: list[Instruction] = []

        # dictionary data structure for mapping btor line id to circt ssa value
        self.line_value_dict = {}

        # dictionary for mapping the btor line id reference (to a sort [type])
        # to an actual circt operation type
        self.line_type_dict = {}

        # Store the generated CIRCT module so that it can later be inspected
        # by automated tests or other parts of the translation flow.
        self.generated_module = None

        # map each btor2 comparison instruction class to the corresponding CIRCT binary operation wrappers
        self.binary_op_dict = {
            Add: comb.AddOp,
            Sub: comb.SubOp,
            And: comb.AndOp,
            Or: comb.OrOp,
            Xor: comb.XorOp,
        }
        
        # Map each btor2 comparison instruction class to the corresponding CIRCT comparison wrapper
        self.comparison_op_dict = {
            Eq: comb.EqOp,
            Neq: comb.NeOp,
            Ult: comb.LtUOp,
            Ulte: comb.LeUOp,
            Ugt: comb.GtUOp,
            Ugte: comb.GeUOp,
            Slt: comb.LtSOp,
            Slte: comb.LeSOp,
            Sgt: comb.GtSOp,
            Sgte: comb.GeSOp,
        }
    def run(self, p: list[Instruction]) -> list[Instruction]:
        
        #Run the generalized BTOR2-to-CIRCT translator as a btor2-opt pass
        self.program = p

        # Clear previous mappings in case the same pass object is reused on a previous btor2 program
        self.line_value_dict.clear()
        self.line_type_dict.clear()
        self.generated_module = None

        # Translate the parsed BTOR2 program into a CIRCT MLIR module
        self.generated_module = self.translate_btor_program()

        # Print the generated module when this pass is executed through the command-line pass infrastructure
        print(self.generated_module)

        # The existing pass pipeline expects each pass to return a list of btor2 Instruction objects. Since this pass generates CIRCT circt ir rather than modifying the BTOR2 program, return the original program

        return p

    #-------------------------------------------------------------------
    def construct_type_dict(self):
        for instruction in self.program:
            if isinstance(instruction,Sort):
                bit_width = instruction.width
                circt_type = IntegerType.get_signless(bit_width)
                self.line_type_dict[instruction.lid] = circt_type

    # constructing input ports in the Module interface:
    # what inputs does this hardware module have?
    def construct_input_ports(self):
        input_ports_gen_list = []

        for instruction in self.program:
            if isinstance(instruction,Input):
                input_type = self.line_type_dict[instruction.sid]
                input_ports_gen_list.append(
                    (instruction.name, input_type)
                )

        return input_ports_gen_list

    # constructing output ports in the Module interface:
    # what outputs does this hardware module have?
    def construct_output_ports(self):
        output_ports_gen_list = []

        for instruction in self.program:
            if isinstance(instruction,Output):

                # instruction itself that's driving the output
                source_instruction = instruction.operands[0]

                # first operand of every instruction producing some value
                # is its Sort (type)
                sort_instruction = source_instruction.operands[0]

                output_type = self.line_type_dict[
                    sort_instruction.lid
                ]

                output_ports_gen_list.append(
                    (instruction.name, output_type)
                )

        return output_ports_gen_list
    # ------------------------------------------------------------------

    # map input PORTS to their SSA values
    def map_input_ports_values(self, block):

        # block arguments correspond to the hardware module input ports
        # (e.g., block.arguments[0] -> %a, block.arguments[1] -> %b)
        block_arg_index = 0

        for instruction in self.program:

            # process every BTOR2 input instruction
            if isinstance(instruction,Input):

                # obtain the corresponding CIRCT SSA value from the
                # module input ports
                input_value = block.arguments[block_arg_index]

                # map the BTOR2 input line ID to its CIRCT SSA value
                # Example: line 2 -> %a, line 3 -> %b
                self.line_value_dict[instruction.lid] = input_value

                # move to the next hardware module input port
                block_arg_index += 1

    def map_output_values(self):
        output_values = []

        for instruction in self.program:
            if isinstance(instruction,Output):

                # obtain the btor2 instruction referenced by this output
                instruction_reference = instruction.operands[0]

                # Look up its already translated circt SSA value
                output_value = self.line_value_dict[
                    instruction_reference.lid
                ]

                output_values.append(output_value)

        return output_values
    #------------------------small helpers------------------------------
    def create_constant(self,const_type, value):
            constant_op = hw.ConstantOp.create(
                        const_type,
                        value,
                    )
            return constant_op.result
    
    def create_comparison(
            self,
            comparison_operation,
            lhs_value,
            rhs_value,
            ):
    
            operation = comparison_operation.create(
            lhs=lhs_value,
            rhs=rhs_value,
            )
    
            return operation.operation.results[0]
    
    #--------------------layer 2: operation translation-----------------

    def translate_binary_operation(self, instruction, circt_operation):
            # operands[1] and operands[2] are the left and right btor2 operands
            left_instruction = instruction.operands[1]
            right_instruction = instruction.operands[2]
    
            # retrieve the circt SSA values previously generated for both operands
            left_value = self.line_value_dict[left_instruction.lid]
            right_value = self.line_value_dict[right_instruction.lid]
    
            # create the corresponding CIRCT binary operation
            operation = circt_operation(
                [left_value, right_value]
            )
    
            # map this btor2 instruction's line ID to the newly generated SSA value
            self.line_value_dict[instruction.lid] = operation.result
    

       # translate btor2 constants into CIRCT SSA values
    def translate_const_operation(self, instruction):

        # Every BTOR2 constant references a sort through instruction.sid
        # Use that sort line ID to obtain the corresponding circt integer type
        constant_type = self.line_type_dict[instruction.sid]

        # Const, Constd, and Consth all store their parsed literal value in instruction.value.
        # parser has already converted the original binary, decimal, or hexadecimal representation into an integer
        constant_op_result = self.create_constant(
            constant_type,instruction.value,)
        # Map the btor2 constant line ID to the generated CIRCT SSA value allowing later operations to use constants through the same
        # line_value_dict lookup used for inputs and prior operation results
        self.line_value_dict[instruction.lid] = constant_op_result


    def translate_special_constant(self, instruction):
        # The first operand is the BTOR2 sort instruction.
        sort_instruction = instruction.operands[0]

        # extract the line id where that sort type was defined
        constant_type = self.line_type_dict[sort_instruction.lid]

        bit_width = constant_type.width

        match instruction: # checking whether instruction object is an object of type 'case'
            # generate a constant value of 0 from btor
            case Zero():
                constant_value = 0

            # generate a constant value of 1 from btor
            case One():
                constant_value = 1

            # generate a constant value of the assigned bit width for this constant in the btor program that is all "ones"
            # to get all 1s, you need 1 less than a power of 2 in binary
            # so create a mask of 1, shift if left by the bit width (up until the MSB of the constant) [(bit_width+1)-value] and obtain a power of 2 where only the MSB = 1
            # then subtract 1 to get a constant [bit_width-value] of all ones (100000000 --> 11111111)
            case Ones():
                # For width 8:
                # (1 << 8) - 1 = 255 = 11111111
                constant_value = (1 << bit_width) - 1

        const_op_result = self.create_constant(
            constant_type,
            constant_value,
        )

        self.line_value_dict[instruction.lid] = const_op_result


    def translate_general_unary_operation(self, instruction):
        # operands[0] is the result sort
        sort_instruction = instruction.operands[0]
        result_type = self.line_type_dict[sort_instruction.lid]
        # operands[1] is the BTOR2 value being operated on
        operand_instruction = instruction.operands[1]
        operand_value = self.line_value_dict[operand_instruction.lid]
        bit_width = result_type.width

        match instruction: # checking whether instruction object is an object of type 'case' 
            case Not():
                # bitwise NOT is same as XORing the original value with an all-ones value because XORing any single bit with 1 will always produce the opposite of that bit -- XOR flips bits
                # so create a constant value of 1s which has width equal to the necessary bit width of the value that we are "Not"ing
                # and XOR both of them
                ones_value = self.create_constant(
                    result_type,
                    (1 << bit_width) - 1,  # value of instruction that should be the constant: 11111111
                )

                operation = comb.XorOp([operand_value, ones_value])

            case Inc():
                # x + 1
                # create constant value 1
                one_value = self.create_constant(result_type, 1)

                # utilize Add operation
                operation = comb.AddOp([operand_value, one_value])

            case Dec():
                # x - 1
                #create constant value 1
                one_value = self.create_constant(
                    result_type,
                    1,
                )
                # utilize Sub operation
                operation = comb.SubOp([operand_value, one_value])

            case Neg():
                # to negate a value x, perform x = 0 - x
                # create constant value 0
                zero_value = self.create_constant(
                    result_type,
                    0,
                )
                # utilize Sub operation
                operation = comb.SubOp(
                    [zero_value, operand_value]
                )
        self.line_value_dict[instruction.lid] = operation.result

    def translate_reduction_unary_operation(self, instruction):
        # operands[0] is the result sort, while operands[1] is the value being reduced
        operand_instruction = instruction.operands[1]

        # obtain circt ssa value that was previously generated for this
        # instruction's line id reference
        operand_value = self.line_value_dict[operand_instruction.lid]

        # obtain operand's integer type so that constants have the same width as operand
        operand_type = operand_value.type
        bit_width = operand_type.width

        # the only time Redor will collapse the whole operand to 0 is if all bits in the operand are 0, so compare the operand against zero
        if isinstance(instruction, Redor):
            zero_value = self.create_constant(
                operand_type,
                0,
            )

            operation_result = self.create_comparison(
                comb.NeOp,
                operand_value,
                zero_value,
            )

        # the only time Redand will collapse the whole operand to 1 is if all bits in the operand are 1, so compare the operand against an all-ones constant.
        elif isinstance(instruction, Redand):
            all_ones_value = self.create_constant(
                operand_type,
                (1 << bit_width) - 1,
            )

            operation_result = self.create_comparison(
                comb.EqOp,
                operand_value,
                all_ones_value,
            )

        # Repeatedly XOR-ing every bit of the operand produces its parity bit; Each 1-bit toggles the result, while each 0-bit leaves it unchanged; Therefore, the final value is 1 if the operand contains an odd number of 1s and 0 if it contains an even number of 1s.
        elif isinstance(instruction, Redxor):
            operation = comb.ParityOp(operand_value)
            operation_result = operation.result

        # Store the one-bit circt ssa result under the BTOR2 instruction's line ID so later instructions can use it
        self.line_value_dict[instruction.lid] = operation_result

    
    def translate_comparison_operation(self,instruction,comparison_op):

        lhs_instruction = instruction.operands[1]
        rhs_instruction = instruction.operands[2]

        lhs_op_value = self.line_value_dict[lhs_instruction.lid]
        rhs_op_value = self.line_value_dict[rhs_instruction.lid]

        
        comp_operation_result = self.create_comparison(
                                        comparison_op,
                                        lhs_op_value,
                                        rhs_op_value,
                                    )

        # update the ssa value for this instruction
        self.line_value_dict[instruction.lid] = comp_operation_result


    def translate_ite_operation(self, instruction):
            # btor: <lid> ite <sort> <condition> <true_value> <false_value>
            #operands[1] is the one-bit select condition that decides which value should be chosen in mux
            condition_instruction = instruction.operands[1]
    
            # operands[2] is the value returned when the condition is 1 (true)
            true_instruction = instruction.operands[2]
    
            # operands[3] is the value returned when the condition is 0 (false)
            false_instruction = instruction.operands[3]
    
            # Earlier translation steps already converted each referenced btor instruction into a circt SSA value and stored it in line_value_dict
            # Retrieve those SSA values so they can be used as operands to comb.mux
            condition_value = self.line_value_dict[
                condition_instruction.lid
            ]
    
            true_value = self.line_value_dict[true_instruction.lid]
    
            false_value = self.line_value_dict[false_instruction.lid]
    
            # Create the corresponding CIRCT mux operation
            # The mux:condition = 1  --> result = true_value
            # condition = 0  --> result = false_value
            # same behavior as btor ite instruction.
            operation = comb.MuxOp.create(
                condition_value,
                true_value,
                false_value,
            )
    
            # The mux produces a new SSA result representing the selected value --> Store that SSA value under this BTOR2 instruction's line ID so any later BTOR2 instruction referring to this ite instruction can look it up in line_value_dict.
            self.line_value_dict[instruction.lid] = (
                operation.operation.results[0]
            )

    def translate_slice_operation(self, instruction):
        # BTOR2 slice form: <lid> slice <sort> <operand> <highbit> <lowbit>
        # operands[0] is the result sort of the extracted bit range
        result_sort_instruction = instruction.operands[0]

        # operands[1] is the original bit-vector that's being sliced
        source_instruction = instruction.operands[1]

        # Retrieve the CIRCT type for the slice result --> extracting bits [7:4] produces a 4-bit result type
        result_type = self.line_type_dict[
            result_sort_instruction.lid
        ]

        # Retrieve the CIRCT SSA value produced for the source BTOR2 instruction
        source_value = self.line_value_dict[
            source_instruction.lid
        ]

        # BTOR2 describes the slice using highbit and lowbit --> CIRCT comb.extract only needs the low-bit offset because the result width is already encoded in result_type
        low_bit = instruction.lowbit

        # create(low_bit, result_type, input) --> btor bits [7:4] --> low_bit = 4, result_type = i4
        operation = comb.ExtractOp.create(
            low_bit,
            result_type,
            source_value,
        )

        # Store the actual MLIR SSA result so later BTOR2 instructions can
        # reference this slice instruction through its line ID.
        self.line_value_dict[instruction.lid] = (
            operation.operation.results[0]
        )

    def translate_concat_operation(self,instruction):
        # btor form: <lid> concat <sort> <op1> <op2>

        # operands[1] becomes upper section of the result
        left_instruction = instruction.operands[1]
        #operands[2] = becomes lower section of the result
        right_instruction = instruction.operands[2]

        #obtain circt SSA values that were previously generated for the operands
        left_value = self.line_value_dict[left_instruction.lid]
        right_value = self.line_value_dict[right_instruction.lid]

        # combine both bitvectors into one wider value of bitwidth = bitwidth of operand 1 + bitwidth of operand 2
        operation = comb.ConcatOp([left_value,right_value])

        # store that new SSA value for wider-bit result so that later btor instructions can use it 
        self.line_value_dict[instruction.lid] = operation.result

    def translate_uext_operation(self, instruction):

        # operands[0] is the result sort type after extending the operand
        result_sort_instruction = instruction.operands[0]

        # operands[1] is the bitvector being extended
        operand_instruction = instruction.operands[1]

        # obtain the existing circt SSA value
        operand_value = self.line_value_dict[
            operand_instruction.lid
        ]

        # If no extension is required, btor2 treats this as judt an alias-holding value - no change
        if instruction.width == 0:
            self.line_value_dict[instruction.lid] = operand_value
            return

        # Create a type for the extension bits
        extension_type = IntegerType.get_signless(
            instruction.width
        )

        # Create a constant containing all zeros to be placed on the left side of the MSB of the current operand
        zero_value = self.create_constant(
            extension_type,
            0,
        )

        # then concatenate the zero bits onto the front of the operand
        operation = comb.ConcatOp(
            [zero_value, operand_value]
        )

        # Store the extended ssa value in the dictionary to be accessed later if needed
        self.line_value_dict[instruction.lid] = operation.result


    def translate_sext_operation(self, instruction):
        # operands[0] is the result sort after sign extension is completed
        result_sort_instruction = instruction.operands[0]

        # operands[1] is the original bitvector being extended
        operand_instruction = instruction.operands[1]

        # obtain the circt SSA value for the original operand
        operand_value = self.line_value_dict[
            operand_instruction.lid
        ]

        # If no additional bits are requested, the sext instruction behaves like an alias-holder so just reuse original SSA value
        if instruction.width == 0:
            self.line_value_dict[instruction.lid] = operand_value
            return

        # get the index of the sign bit of the operand -- the MSB of the original operand; i4 value --> its bit index is 3
        operand_width = operand_value.type.width
        sign_bit_index = operand_width - 1

        # Extract exactly one bit from the most-significant position.
        sign_bit_type = IntegerType.get_signless(1)

        sign_bit_operation = comb.ExtractOp.create(
            sign_bit_index,
            sign_bit_type,
            operand_value,
        )

        sign_bit_value = sign_bit_operation.operation.results[0]

        # Create a type with a width equal to the number of extension bits --> ReplicateOp uses this result width to determine how many copies of the one-bit sign value should be produced.
        extension_type = IntegerType.get_signless(
            instruction.width
        )

        # Repeat the sign bit until the new upper bits are filled up
        replicated_sign_operation = comb.ReplicateOp(
            extension_type,
            sign_bit_value,
        )

        replicated_sign_value = replicated_sign_operation.result

        # put the replicated sign bits in front of the original operand
        concat_operation = comb.ConcatOp(
            [replicated_sign_value, operand_value]
        )

        # Store the sign-extended SSA value so later btor instructions can reference this sext instruction if needed
        self.line_value_dict[instruction.lid] = concat_operation.result
    
    #-------------------------------------------------------------------
    # replace translate_add_instruction() with the following method which now utilizes the generalized translate_binary_operation() function
    def translate_any_binary_instruction(self):
        for instruction in self.program:
            instruction_type = type(instruction)

            if instruction_type in self.binary_op_dict:
                self.translate_binary_operation(
                    instruction,
                    self.binary_op_dict[instruction_type],
                )
        
    def translate_any_const_instruction(self):
            for instruction in self.program:
    
                if isinstance(instruction, (Const, Constd, Consth)):
                    self.translate_const_operation(instruction)

    def translate_any_unary_instruction(self):
        specific_const_unary_ops_tuple = (Zero,One,Ones)
        general_unary_ops_tuple = (Not,Inc,Dec,Neg)
        reduction_unary_ops_tuple = (Redor,Redand,Redxor)
        for instruction in self.program:
            if isinstance(instruction,specific_const_unary_ops_tuple):
                self.translate_special_constant(instruction)
            elif isinstance(instruction,general_unary_ops_tuple):
                self.translate_general_unary_operation(instruction)
            elif isinstance(instruction,reduction_unary_ops_tuple):
                self.translate_reduction_unary_operation(instruction)

    def translate_any_comparison_instruction(self):
        
        for instruction in self.program:
            instruction_type = type(instruction)
            if instruction_type in self.comparison_op_dict:
                self.translate_comparison_operation(instruction, comparison_op=self.comparison_op_dict[instruction_type])
    #-------------------------------------------------------------------
    def translate_instructions_in_program_order(self):
        """
        Translate value-producing BTOR2 instructions once, in the order in which they show up in the original program

        Since BTOR2 instructions can only reference previously defined line IDs, each operand's CIRCT SSA value should already exist in
        line_value_dict when the instruction is reached.
        """

        constant_op_types = (Const, Constd, Consth)
        special_constant_op_types = (Zero, One, Ones)
        general_unary_op_types = (Not, Inc, Dec, Neg)
        reduction_unary_op_types = (Redor, Redand, Redxor)

        for instruction in self.program:
            instruction_type = type(instruction)

            # Sorts were already processed while constructing line_type_dict
            if isinstance(instruction, Sort):
                continue

            # Inputs were already mapped to the hw.module block arguments
            elif isinstance(instruction, Input):
                continue

            # Outputs are handled after all the value-producing instructions have been translated
            elif isinstance(instruction, Output):
                continue

            elif isinstance(instruction, constant_op_types):
                self.translate_const_operation(instruction)

            elif isinstance(instruction, special_constant_op_types):
                self.translate_special_constant(instruction)

            elif isinstance(instruction, general_unary_op_types):
                self.translate_general_unary_operation(instruction)

            elif isinstance(instruction, reduction_unary_op_types):
                self.translate_reduction_unary_operation(instruction)

            elif instruction_type in self.binary_op_dict:
                self.translate_binary_operation(
                    instruction,
                    self.binary_op_dict[instruction_type],
                )

            elif instruction_type in self.comparison_op_dict:
                self.translate_comparison_operation(
                    instruction,
                    self.comparison_op_dict[instruction_type],
                )

            elif isinstance(instruction, Ite):
                self.translate_ite_operation(instruction)

            elif isinstance(instruction, Slice):
                self.translate_slice_operation(instruction)

            elif isinstance(instruction, Concat):
                self.translate_concat_operation(instruction)

            elif isinstance(instruction, Uext):
                self.translate_uext_operation(instruction)

            elif isinstance(instruction, Sext):
                self.translate_sext_operation(instruction)

    def translate_btor_program(self):

        with Context() as ctx, Location.unknown():

            # register all CIRCT dialects
            # (hw, comb, seq, sv, ...) so that these operations can be created
            circt.register_dialects(ctx)

            # Build the CIRCT type map from the BTOR2 sort instructions.
            # This replaces manually creating a fixed type such as:
            # i8 = IntegerType.get_signless(8)
            self.construct_type_dict()

            #print("Type map:", self.line_type_dict)

            input_ports_list = self.construct_input_ports()
            output_ports_list = self.construct_output_ports()
            
            module = Module.create()

            # new operations inserted into the module body
            with InsertionPoint(module.body):

                # create hardware module
                # corresponds to: hw.module @comb_adder()
                adder = hw.HWModuleOp(
                    name="comb_adder",

                    # input_ports_list returned from
                    # construct_input_ports()
                    input_ports=input_ports_list,

                    # output_ports_list returned from
                    # construct_output_ports()
                    output_ports=output_ports_list,
                )

            # Since the Region initially contains no blocks,
            # we must explicitly create one.
            block = adder.add_entry_block()

            with InsertionPoint(block):

                # with automatic input SSA value mapping
                self.map_input_ports_values(block)
        
                # Translate every value-producing BTOR2 instruction once, in the same order in which it appears in the original btor program
                #help(comb.MuxOp)
                #help(comb.ExtractOp)
                #print(hasattr(comb.ExtractOp, "create"))
                #help(comb.ConcatOp)
                #help(comb.ReplicateOp)
                self.translate_instructions_in_program_order()
                                
                # create hardware output operation
                # hw.output %0, where %0 is the translated output value
                # automatic output SSA value collection
                output_values = self.map_output_values()
                #for value in output_values:
                 #                   print(value)
                  #                  print(type(value))
                                    
                hw.OutputOp(output_values)

            # return the generated MLIR module to run(), where it is stored in self.generated_module
            return module