##########################################################################
# BTOR2 parser, code optimizer, and circuit miter
#
# Copyright (C) 2026  Amelia Dobis, Nidhi Lawange
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
##########################################################################

# Generalized an scalable btor2-to-mlir translator that converts 
# btor2 programs into semantically equivalent circt ir using core circt # dialects.

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

from circt.dialects import hw, comb, verif, seq

from circt.support import BackedgeBuilder, connect

# Import the existing btor2-opt pass interface.
from ...passes.genericpass import Pass
from ...program import Instruction, Sort, Input, Output, Add, Sub, And, Or, Xor, Const, Constd, Consth, Zero, One, Ones, Not, Inc, Dec, Neg, Redor, Redand, Redxor, Eq, Neq, Ugt, Ugte, Ult, Ulte, Sgt, Sgte, Slt, Slte, Ite, Slice, Concat, Uext, Sext, Mul, Udiv, Sdiv, Urem, Srem, Sll, Srl, Sra, Implies, Constraint, Bad, State, Init, Next, Read, Write

circt_sort_types = {
    "bv": {"bitvector","bitvec"},
    "array": {"array"}
}

# The generalized translator now inherits from Pass so it can be invoked
# through the existing btor2-opt pass infrastructure.
class Btor2CirctTranslator(Pass):

    def __init__(self):
        """
        Initializes BTOR2-to-CIRCT Core translator and the dictionaries for instruction mappings.
        """
        # Name used to identify this pass in the pass infrastructure.
        super().__init__("emit-circt-core")

        # The parsed BTOR2 program is supplied by the pass infrastructure
        # when run() is called.
        self.program: list[Instruction] = []

        # dictionary data structure for mapping btor line id to circt ssa value
        self.line_value_dict = {}

        # dictionary for mapping the btor line id reference (to a sort [type])
        # to an actual circt operation type
        self.line_type_dict = {}

        # store state-related information from btor2 while translating the state, init, and next instructions that it's associated with
        self.state_dict = {}

        # store circt ssa value corresponding to implicit clock input that will be added to only state-dependent btor2 programs 
        self.clock_value = None
        
        # store temporary backedge that represents the current state values at the same time that the combinational next state logic is being translated
        self.state_register_dict = {}

        # Store the generated CIRCT module so that it can later be inspected
        # by automated tests or other parts of the translation flow.
        self.generated_module = None
        self.module_name = ""

        # map each btor2 comparison instruction class to the corresponding CIRCT binary operation wrappers

        # circt operations whose Python wrappers take a sequence of operands - list of operands
        self.varied_binary_op_dict = {
            Add: comb.AddOp,
            Sub: comb.SubOp,
            Mul: comb.MulOp,
            And: comb.AndOp,
            Or: comb.OrOp,
            Xor: comb.XorOp,
        }
        # CIRCT operations whose Python wrappers take explicit lhs and rhs operands - 2 distinct arguments
        self.fixed_binary_op_dict = {
            Udiv: comb.DivUOp,
            Sdiv: comb.DivSOp,
            Urem: comb.ModUOp,
            Srem: comb.ModSOp,
            # logical and arithmetic shift operations
            Sll: comb.ShlOp,
            Srl: comb.ShrUOp,
            Sra: comb.ShrSOp,
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
        """
        Performs the task of the CIRCT emitter via the btor2-opt pass structure.

        Args: p: parsed BTOR2 program which is a list of the instructions.

        Returns: list[Instruction]: the original BTOR2 program.
        """

        #Run the generalized BTOR2-to-CIRCT translator as a btor2-opt pass
        self.program = p

        # Clear previous mappings in case the same pass object is reused on a previous btor2 program
        self.line_value_dict.clear()
        self.line_type_dict.clear()
        self.state_dict.clear()
        self.state_register_dict.clear()
        # clear previously stored clock SSA value for next btor program
        self.clock_value = None
        self.generated_module = None

        # Translate the parsed BTOR2 program into a CIRCT MLIR module
        self.generated_module = self.translate_btor_program()

        # Print the generated module when this pass is executed through the command-line pass infrastructure
        print(self.generated_module)

        # The existing pass pipeline expects each pass to return a list of btor2 Instruction objects. Since this pass generates CIRCT circt ir rather than modifying the BTOR2 program, return the original program

        return p

    #-------------------------------------------------------------------
    def construct_type_dict(self):
        """
        Construct CIRCT types corresponding to BTOR2 sort declarations.

        Iterates through BTOR2 program and maps each sort's line ID to its corresponding CIRCT type.

        Returns: None. Populates line_value_dict and stores the clock SSA value separately when the program contains state instructions.
        """
        for instruction in self.program:
            if isinstance(instruction,Sort):

                if instruction.typ in circt_sort_types["array"]:
                    element_type = self.line_type_dict[instruction.sort_element.lid]

                    addr_width = instruction.sort_addr.width
                    array_size = 1 << addr_width

                    circt_type = hw.ArrayType.get(element_type, array_size)
                else:
                    bit_width = instruction.width
                    circt_type = IntegerType.get_signless(bit_width)
                    
                self.line_type_dict[instruction.lid] = circt_type

    def construct_input_ports(self):
        """
    Construct input port definitions for the CIRCT HW module.

    Includes BTOR2 input declarations and an implicit clock port when the program contains state instructions.

    Returns a list: tuples containing each port's name and CIRCT type
    """
        input_ports_gen_list = []

        for instruction in self.program:
            if isinstance(instruction,Input):
                input_type = self.line_type_dict[instruction.sid]
                input_ports_gen_list.append(
                    (instruction.name, input_type)
                )
        if self.state_dict:
            # construct the circt clock type
            clock_type = seq.ClockType.get()
            input_ports_gen_list.append(("clk",clock_type))


        return input_ports_gen_list

    
    def construct_output_ports(self):
        """
    Construct output port definitions for the CIRCT HW module.

    Determines each output's type from the BTOR2 instruction referenced by its output declaration.

    Returns a list: tuples containing each port's name and CIRCT type.
    """
        output_ports_gen_list = []

        for instruction in self.program:
            if isinstance(instruction,Output):

                source_instruction = instruction.operands[0]
                sort_instruction = source_instruction.operands[0]

                output_type = self.line_type_dict[
                    sort_instruction.lid
                ]

                output_ports_gen_list.append(
                    (instruction.name, output_type)
                )

        return output_ports_gen_list

    # -------------------Mapping SSA Values------------------------

    def map_input_ports_values(self, block):
        """
        Map BTOR input line IDs to CIRCT HW module block arguments.

        Args: block: entry block of the generated CIRCT HW module.

        Returns None. Populates line_value_dict and stores the clock SSA value separately when the program contains state instructions.
        """
        block_arg_index = 0

        for instruction in self.program:

            if isinstance(instruction,Input):

                input_value = block.arguments[block_arg_index]
                self.line_value_dict[instruction.lid] = input_value
                block_arg_index += 1

        if self.state_dict:
            self.clock_value = block.arguments[block_arg_index]

    def map_output_values(self):
        """
        Collect CIRCT SSA values corresponding to BTOR2 output declarations.

        Returns a list: CIRCT SSA values ordered according to the module's output port declarations.
        """
        output_values = []
        for instruction in self.program:
            if isinstance(instruction,Output):

                instruction_reference = instruction.operands[0]
                output_value = self.line_value_dict[
                    instruction_reference.lid
                ]
                output_values.append(output_value)

        return output_values

    #----------------State-Related Helper Functions----------------
    def get_state_info(self):
        """
        Obtain BTOR2 state declarations, the initialization of the state and next-state instructions.

        Returns: None. Populates state_dict with initial and next state information.
        """
        for instruction in self.program:

            # found a state instruction in the btor input --> start with adding to the state dictionary definitions
            if isinstance(instruction, State):
                self.state_dict[instruction.lid] = {
                    "state_instruction": instruction,
                    "init_instruction": None,
                    "next_instruction": None,
                }
            # init becomes the second entry of the state dictionary that is associated with that instruction that is being stored in the first entry of dictionary
            elif isinstance(instruction, Init):
                state_instruction = instruction.operands[1]
                self.state_dict[state_instruction.lid]["init_instruction"] = instruction

            elif isinstance(instruction, Next):
                state_instruction = instruction.operands[1]
                self.state_dict[state_instruction.lid]["next_instruction"] = instruction
        
    
    def create_state_backedges(self):
        """
        Helper method for creating CIRCT representations of the BTOR2 state declarations.

        Instantiates high level memory blocks for array states and creates temporary SSA backedges for bitvector states since their register blocks are constructed later.

        Returns: None. Updates line_value_dict and state_register_dict.
        """

        for state_instr_lid, state_info in self.state_dict.items():
            state_instruction = state_info["state_instruction"]

            state_sort = state_instruction.operands[0]
            state_type = self.line_type_dict[state_instruction.sid]

            if state_sort.typ in circt_sort_types["array"]:
                element_type = self.line_type_dict[state_sort.sort_element.lid]

                addr_width = state_sort.sort_addr.width
                array_size = 1 << addr_width

                memory_type = seq.HLMemType.get([array_size],element_type)

                reset = hw.ConstantOp.create(IntegerType.get_signless(1),0)

                memory = seq.HLMemOp(memory_type,self.clock_value,reset.result,state_instruction.name,)
                self.line_value_dict[state_instruction.lid] = memory.handle
            else:
                state_backedge = BackedgeBuilder.create(
                    state_type,
                    state_instruction.name,
                    None,
                )

                self.state_register_dict[state_instruction.lid] = state_backedge

                self.line_value_dict[state_instruction.lid] = (
                    state_backedge.result
                )


    #---------small helpers for some translation functions----------
    def create_constant(self,const_type, value):
        """
        Creates a CIRCT HW constant.

        Args: 
            const_type: CIRCT integer type of the constant.
            value: Integer value of the constant.
            
        Returns: CIRCT SSA value produced by the constant making operation.
        """
        constant_op = hw.ConstantOp.create(const_type,value,)
        return constant_op.result
    
    def create_comparison(
            self,
            comparison_operation,
            lhs_value,
            rhs_value,
            ):
        """
        Creates a CIRCT comparison operation.

        Args: comparison_operation: the CIRCT comparison operation class.
        lhs_value: Left operand SSA value.
        rhs_value: Right operand SSA value.

        Returns: CIRCT SSA value holding comparison result.
        """
    
        operation = comparison_operation.create(lhs=lhs_value,rhs=rhs_value,)
    
        return operation.operation.results[0]
    
    
    #--------------------layer 2: operation translation-----------------

    def extract_binary_operands(self, instruction):
            """
            Obtain the CIRCT SSA values of BTOR2 binary instruction's operands.

            Args: instruction: BTOR2 binary instruction.

            Returns: tuple: left and right operand CIRCT SSA values.
            """
            left_instruction = instruction.operands[1]
            right_instruction = instruction.operands[2]
            
            left_op_value = self.line_value_dict[left_instruction.lid]
            right_op_value = self.line_value_dict[right_instruction.lid]

            return left_op_value,right_op_value

    def translate_varied_binary_operation(self, instruction, circt_operation):
        """
        Translate the BTOR2 binary operations whose CIRCT wrappers accept a sequence of operands.

        Args:
            instruction: BTOR2 binary instruction.
            circt_operation: the corresponding CIRCT operation class.
        
        Returns: None. Stores the result in line_value_dict.
        """

        left_op_value, right_op_value = self.extract_binary_operands(instruction)

        operation = circt_operation(
            [left_op_value, right_op_value]
        )

        self.line_value_dict[instruction.lid] = operation.result

    def translate_fixed_binary_operation(self, instruction, circt_operation):
        """
        Translate BTOR binary operations whose CIRCT wrappers accept separate left and right operands.

        Args: 
            instruction: BTOR2 binary instruction.
            circt_operation: the corresponding CIRCT operation class.
        
        Returns: None. Stores the result in line_value_dict.
        """

        left_op_value, right_op_value = self.extract_binary_operands(instruction)

       
        operation = circt_operation(
            left_op_value,
            right_op_value
        )

        self.line_value_dict[instruction.lid] = operation.result


    def translate_const_operation(self, instruction):
        """
        Translate BTOR2 const, constd, consth instructions into CIRCT HW constants.

        Args: instruction: BTOR2 constant instruction.

        Returns: None. Stores the constant SSA values in line_value_dict.
        """

        constant_type = self.line_type_dict[instruction.sid]

        constant_op_result = self.create_constant(
            constant_type,instruction.value,)

        self.line_value_dict[instruction.lid] = constant_op_result


    def translate_special_constant(self, instruction):
        """
        Translate BTOR2 zero, one, and ones instructions into CIRCT constants.

        Args: instruction: BTOR2 special constant instruction.

        Returns: None. Stores the constant SSA value in line_value_dict.
        """
        sort_instruction = instruction.operands[0]

        constant_type = self.line_type_dict[sort_instruction.lid]

        bit_width = constant_type.width

        match instruction: 
            case Zero():
                constant_value = 0

            case One():
                constant_value = 1

            # to get all 1s, you need 1 less than a power of 2 in binary
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
        """
        Translate BTOR not, inc, dec, and neg instructions using CIRCT combinational operations.

        Args: instruction: BTOR2 unary instruction.

        Returns: None. Stores the resulting SSA value in line_value_dict.
        """
        sort_instruction = instruction.operands[0]
        result_type = self.line_type_dict[sort_instruction.lid]
        operand_instruction = instruction.operands[1]
        operand_value = self.line_value_dict[operand_instruction.lid]
        bit_width = result_type.width

        match instruction: 
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
                one_value = self.create_constant(result_type, 1)

                operation = comb.AddOp([operand_value, one_value])

            case Dec():
                one_value = self.create_constant(
                    result_type,
                    1,
                )
                operation = comb.SubOp([operand_value, one_value])

            case Neg():
                # to negate a value x, perform x = 0 - x
                zero_value = self.create_constant(
                    result_type,
                    0,
                )
                operation = comb.SubOp(
                    [zero_value, operand_value]
                )
        self.line_value_dict[instruction.lid] = operation.result

    def translate_reduction_unary_operation(self, instruction):
        """
        Translate BTOR2 reduction operations into CIRCT comparisons or parity operations.

        Args: instruction: BTOR2 redor, redand, or redxor instruction.

        Returns: None. Stores the one-bit result in line_value_dict.
        """
        operand_instruction = instruction.operands[1]

        operand_value = self.line_value_dict[operand_instruction.lid]

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
        # only time Redand collapses the entire operand to 1 is if all bits in the operand are 1, so compare the operand against an all-ones constant
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

        # XOR ing each bit of the operand repeatedly which gives the parity bit; Each 1-bit toggles the result, while each 0-bit leaves it unchanged; Therefore, the final value is 1 if the operand contains an odd number of 1s and 0 if it contains an even number of 1s.
        elif isinstance(instruction, Redxor):
            operation = comb.ParityOp(operand_value)
            operation_result = operation.result

        self.line_value_dict[instruction.lid] = operation_result

    
    def translate_comparison_operation(self,instruction,comparison_op):
        """
        Translate BTOR2 signed, unsigned, and equality comparisons.

        Args:
            instruction: BTOR2 comparison instruction.
            comparison_op: the corresponding CIRCT comparison operation class.

        Returns: None. Stores the comparison result in line_value_dict.
        """

        lhs_instruction = instruction.operands[1]
        rhs_instruction = instruction.operands[2]

        lhs_op_value = self.line_value_dict[lhs_instruction.lid]
        rhs_op_value = self.line_value_dict[rhs_instruction.lid]

        
        comp_operation_result = self.create_comparison(
                                        comparison_op,
                                        lhs_op_value,
                                        rhs_op_value,
                                    )

        self.line_value_dict[instruction.lid] = comp_operation_result



    def translate_ite_operation(self, instruction):
        """
        Translate a BTOR2 if-then-else instruction into a CIRCT combinational MUX.

        Args: instruction: BTOR2 ite instruction.

        Returns: None. Stores the selected value from the mux in line_value dict.
        """
        condition_instruction = instruction.operands[1]
        true_instruction = instruction.operands[2]
        false_instruction = instruction.operands[3]
    
        condition_value = self.line_value_dict[condition_instruction.lid]
    
        true_value = self.line_value_dict[true_instruction.lid]
        false_value = self.line_value_dict[false_instruction.lid]
    
        operation = comb.MuxOp.create(
            condition_value,
            true_value,
            false_value,
        )
    
        self.line_value_dict[instruction.lid] = (
            operation.operation.results[0]
        )

    def translate_slice_operation(self, instruction):
        """
        Translate BTOR2 bitvector slice into a CIRCT extract operation.

        Args: instruction: BTOR2 slice instruction.

        Returns: None. Stores the extracted the SSA value in line-value_dict.
        """

        result_sort_instruction = instruction.operands[0]
        source_instruction = instruction.operands[1]
        result_type = self.line_type_dict[
            result_sort_instruction.lid
        ]

        source_value = self.line_value_dict[
            source_instruction.lid
        ]

        # BTOR2 describes the slice using highbit and lowbit --> CIRCT comb.extract only needs the low-bit offset because the result width is already encoded in result_type
        low_bit = instruction.lowbit

        operation = comb.ExtractOp.create(
            low_bit,
            result_type,
            source_value,
        )

        self.line_value_dict[instruction.lid] = (
            operation.operation.results[0]
        )

    def translate_concat_operation(self,instruction):
        """
        Translate BTOR2 bitvector concatenation into a CIRCT concat operation.

        Args: instruction: BTOR2 concat instruction.

        Returns: None. Stores the concatenated SSA value in line_value_dict.
        """
        left_instruction = instruction.operands[1]
        right_instruction = instruction.operands[2]

        left_value = self.line_value_dict[left_instruction.lid]
        right_value = self.line_value_dict[right_instruction.lid]

        operation = comb.ConcatOp([left_value,right_value])

        self.line_value_dict[instruction.lid] = operation.result

    def translate_uext_operation(self, instruction):
        """
        Translate BTOR2 unsigned extension by prepending zero bits.

        Args: instruction: BTOR2 Uext instruction.

        Returns: None. Stores the zero-extended SSA value in line_value_dict.
        """
        result_sort_instruction = instruction.operands[0]
        operand_instruction = instruction.operands[1]

        operand_value = self.line_value_dict[
            operand_instruction.lid
        ]

        if instruction.width == 0:
            self.line_value_dict[instruction.lid] = operand_value
            return

        extension_type = IntegerType.get_signless(
            instruction.width
        )

        zero_value = self.create_constant(
            extension_type,
            0,
        )

        operation = comb.ConcatOp(
            [zero_value, operand_value]
        )

        self.line_value_dict[instruction.lid] = operation.result


    def translate_sext_operation(self, instruction):
        """
        Translate BTOR2 signed extension by replicating the operand's sign bit.

        Args: instruction: BTOR2 sext instruction.

        Returns: None. Stores the sign-extended SSA value in line_value_dict.
        """
        result_sort_instruction = instruction.operands[0]
        operand_instruction = instruction.operands[1]

        operand_value = self.line_value_dict[
            operand_instruction.lid
        ]

        if instruction.width == 0:
            self.line_value_dict[instruction.lid] = operand_value
            return

        operand_width = operand_value.type.width
        sign_bit_index = operand_width - 1
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
        replicated_sign_operation = comb.ReplicateOp(
            extension_type,
            sign_bit_value,
        )
        replicated_sign_value = replicated_sign_operation.result
        concat_operation = comb.ConcatOp(
            [replicated_sign_value, operand_value]
        )

        self.line_value_dict[instruction.lid] = concat_operation.result

    def translate_implies_operation(self, instruction):
        """
        Translate BTOR2 logical implication using bitwise NOT and OR equivalent operations.

        Args: instruction: BTOR2 implies operation.

        Returns: None. Stores the implication result in line_value_dict.
        """
        left_instruction = instruction.operands[1]
        right_instruction = instruction.operands[2]

        left_op_value = self.line_value_dict[left_instruction.lid]
        right_op_value = self.line_value_dict[right_instruction.lid]

        sort_instruction = instruction.operands[0]
        result_type = self.line_type_dict[sort_instruction.lid]

        bit_width = result_type.width

        all_ones_value = (1 << bit_width) - 1

        all_ones = self.create_constant(
            result_type,
            all_ones_value,
        )

        not_left = comb.XorOp(
            [left_op_value, all_ones]
        )

        implication = comb.OrOp(
            [not_left.result, right_op_value]
        )

        self.line_value_dict[instruction.lid] = implication.result

    def translate_constraint_operation(self, instruction):
        """
        Translate a BTOR2 constraint into a CIRCT verification assumption.

        Args: instruction: BTOR2 constraint instruction.

        Returns: None. Emits the verif.assume operation.
        """
        condition_instruction = instruction.operands[0]
        condition_value = self.line_value_dict[condition_instruction.lid]

        verif.AssumeOp(condition_value)

    def translate_bad_operation(self, instruction):
        """
        Translate BTOR2 bad-state condition into CIRCT verification assertion that ensures that the condition is false.

        Args: instruction: BTOR2 bad instruction.

        Returns: None. Emits the verif.assert operation.
        """
        condition_instruction = instruction.operands[0]
        condition_value = self.line_value_dict[condition_instruction.lid]

        print("condition_value =", condition_value)
        print("condition_value type =", type(condition_value))
        print("condition lid =", condition_instruction.lid)
        condition_type = condition_value.type
        
        bit_width = condition_type.width
        ones_value = self.create_constant(
            condition_type,
            (1 << bit_width) - 1,  # value of instruction that should be the constant: 1
            )
        
        inverted_condition = comb.XorOp([condition_value, ones_value])
        
        # Assert that the bad condition never will be true
        verif.AssertOp(
            inverted_condition.result
        )
    
    def translate_any_state_instruction(self):
        """
        Build CIRCT memory-based operations for BTOR2 state updates.

        Translates supported array-based state writes into memory block write ports and bitvector-based state updates into register blocks. 

        Returns: None. Updates state-related SSA value mappings and produces state-based operations.
        """
        for state_instr_lid, state_info in self.state_dict.items():
            state_instruction = state_info["state_instruction"]
            init_instruction = state_info["init_instruction"]
            next_instruction = state_info["next_instruction"]

            state_sort = state_instruction.operands[0]

            if state_sort.typ in circt_sort_types["array"]:
                next_state_instruction = next_instruction.operands[2]
            
                if isinstance(next_state_instruction, Write):
                    memory_instr = next_state_instruction.operands[1]
                    index_instr = next_state_instruction.operands[2]
                    element_instr = next_state_instruction.operands[3]

                    memory_val = self.line_value_dict[memory_instr.lid]
                    index_val = self.line_value_dict[index_instr.lid]
                    element_val = self.line_value_dict[element_instr.lid]

                    write_en = self.create_constant(IntegerType.get_signless(1),1,)

                    seq.WritePortOp(memory_val, [index_val], element_val, write_en, 1,)

                continue

            state_type = self.line_type_dict[state_instruction.sid]
            next_state_instruction = next_instruction.operands[2]
            next_state_instruction_value = self.line_value_dict[next_state_instruction.lid]

            init_value = None
            
            if init_instruction is not None:
                init_instruction = init_instruction.operands[2]
                init_value = self.line_value_dict[
                    init_instruction.lid
                ]

            # Now both values required to construct the real register are available:
            # input          = translated btor2 next-state value
            # clk            = clock input added by translator
            # power_on_value = translated btor2 init value (if there)
            # CompRegOp constructor handles power_on_value and converts a constant initialization value into the !seq.immutable representation required by circt
            if init_value is not None:
                state_register = seq.CompRegOp(
                    state_type,
                    input=next_state_instruction_value,
                    clk=self.clock_value,
                    power_on_value=init_value,
                    name=state_instruction.name,
                )
            else:
                state_register = seq.CompRegOp(
                    state_type,
                    input=next_state_instruction_value,
                    clk=self.clock_value,
                    name=state_instruction.name,
                )

            state_backedge = self.state_register_dict[state_instruction.lid]
            state_backedge.result.replace_all_uses_with(state_register.data)
            state_backedge.erase()

            self.line_value_dict[state_instruction.lid] = (state_register.data)
            
    def translate_readArr_operation(self, instruction):
        """
        Translate BTOR2 array reads into CIRCT HW array accesses or Seq memory block read ports, based on what the representation of the source array is.

        Args: instruction: BTOR2 Read instruction.

        Returns: None. Stores the read result in line_value_dict.
        """
        memory_instr = instruction.operands[1]
        memory_val = self.line_value_dict[instruction.operands[1].lid]
        index_val = self.line_value_dict[instruction.operands[2].lid]

        result_typ = self.line_type_dict[instruction.operands[0].lid]

        if isinstance(memory_instr, State):
            read_operation = seq.ReadPortOp(result_typ, memory_val,[index_val],0)
            result_val = read_operation.readData
        else:
            read_operation = hw.ArrayGetOp(memory_val, index_val)
            result_val = read_operation.result

        self.line_value_dict[instruction.lid] = result_val

    
    #-------------------------------------------------------------------
    
    def translate_instructions_in_program_order(self):
        """
        Translate all supported BTOR2 instructions in program order using their previously generated CIRCT SSA values, while handling the sequential state instruction updates and module outputs in later state translation stages.
        
        Returns: None. Populates line_value_dict and produces the CIRCT operations.
        """

        constant_op_types = (Const, Constd, Consth)
        special_constant_op_types = (Zero, One, Ones)
        general_unary_op_types = (Not, Inc, Dec, Neg)
        reduction_unary_op_types = (Redor, Redand, Redxor)

        for instruction in self.program:
            instruction_type = type(instruction)

            if isinstance(instruction, Sort):
                continue

            elif isinstance(instruction, Input):
                continue

            elif isinstance(instruction, Output):
                continue
            
            # handled through a sequence of required helper functions for translating this set of sequential instructions
            elif isinstance(instruction, (State,Init,Next)):
                continue # because if a state instruction is found, we cannot directly translate it -- still have to create a backedge that we replace later and then produce the final result value for a particular state instruction to which another Init and Next instruction are associated
            
            elif instruction.lid in self.line_value_dict:
                # some instructions used as state initialization values may have already been translated before creating the state register
                    continue

            elif isinstance(instruction, constant_op_types):
                self.translate_const_operation(instruction)

            elif isinstance(instruction, special_constant_op_types):
                self.translate_special_constant(instruction)

            elif isinstance(instruction, general_unary_op_types):
                self.translate_general_unary_operation(instruction)

            elif isinstance(instruction, reduction_unary_op_types):
                self.translate_reduction_unary_operation(instruction)

            elif instruction_type in self.fixed_binary_op_dict:
                self.translate_fixed_binary_operation(
                    instruction,
                    self.fixed_binary_op_dict[instruction_type],
                )

            elif instruction_type in self.varied_binary_op_dict:
                self.translate_varied_binary_operation(
                    instruction,
                    self.varied_binary_op_dict[instruction_type],
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

            elif isinstance(instruction, Implies):
                self.translate_implies_operation(instruction)

            elif isinstance(instruction, Constraint):
                self.translate_constraint_operation(instruction)

            elif isinstance(instruction, Bad):
                self.translate_bad_operation(instruction)
            
            elif isinstance(instruction, Read):
                self.translate_readArr_operation(instruction)
            
            elif isinstance(instruction, Write):
                continue
            
            
    def translate_btor_program(self):
        """
        Translate the parsed BTOR2 program into CIRCT MLIR.

        Facilitates type mapping, module interface construction, SSA value mapping, combinational programs, sequential state programs, and output construction.

        Returns: CIRCT MLIR module holding the translated hardware design.
        """
        with Context() as ctx, Location.unknown():

            circt.register_dialects(ctx)

            self.construct_type_dict()

            self.get_state_info()
            input_ports_list = self.construct_input_ports()
            output_ports_list = self.construct_output_ports()
            
            module = Module.create()

            with InsertionPoint(module.body):
               
                hw_module = hw.HWModuleOp(
                    self.module_name,
                    input_ports=input_ports_list,
                    output_ports=output_ports_list,
                )
            block = hw_module.add_entry_block()

            with InsertionPoint(block):
                self.map_input_ports_values(block)

                # Keep a BackedgeBuilder active while creating registers whose next-state inputs are not available yet; circt stores these unresolved inputs as temporary backedges until connect() replaces them with the translated next-state ssa values
                with BackedgeBuilder(self.module_name):            
                    self.create_state_backedges()
                    self.translate_instructions_in_program_order()

                # since all next-state and init-state operations have stored corresponding circt ssa values, can now create the actual seq.compreg operations and replace the earlier generated temporary backedge values
                    self.translate_any_state_instruction()

                output_values = self.map_output_values()
                hw.OutputOp(output_values)

            return module