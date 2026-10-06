# ========================================================================
# Nidhi Lawange
#
# Description:
# Prototype BTOR2-to-CIRCT translation pass that identifies a simple
# combinational adder in a parsed BTOR2 program and generates the equivalent
# CIRCT MLIR representation as text. This implementation demonstrates the
# overall translation workflow and served as the initial proof-of-concept
# before developing the generalized BTOR2-to-CIRCT translator.
# ========================================================================
from ...passes.genericpass import Pass
from ...program import Instruction, Input, Output, Add, State, Init, Constd

class CombAdder(Pass):
    def __init__(self):
        super().__init__("comb-adder")
    
    def run(self, program: list[Instruction]) -> list[Instruction]:
        print("comb-adder pass running")
        # store all btor2 input instructions in this list - will later become the input ports of CIRCT's hw.module
        inputs = []

        # store the btor2 add instruction - will later become a CIRCT hw.module comb.add operation
        add_instruction = None

        # store the btor output instruction - will later become a CIRCT hw.output instruction
        output_instruction = None

        # iterate through every parsed btor2 instruction object
        for instruction in program:
            if isinstance(instruction,Input):
                inputs.append(instruction)
            elif isinstance(instruction, Add):
                add_instruction = instruction
            elif isinstance(instruction,Output):
                output_instruction = instruction
        
        if len(inputs) != 2:
            raise ValueError("Expected exactly two inputs")

        if add_instruction is None:
            raise ValueError("Expected one Add instruction")

        if output_instruction is None:
            raise ValueError("Expected one Output instruction")

        # BTOR2 add format:
        # 4 add 1 2 3
        # operands[0] = sort/type
        # operands[1] = left input
        # operands[2] = right input
        add_sort = add_instruction.operands[0]
        add_left = add_instruction.operands[1]
        add_right = add_instruction.operands[2]

        # Convert BTOR2 sort bitvec 8 into CIRCT/MLIR type i8
        circt_type = f"i{add_sort.width}"

        # Convert BTOR2 input objects into CIRCT SSA-style names
        left_name = f"%{add_left.name}"
        right_name = f"%{add_right.name}"

        print("CIRCT type:", circt_type)
        print("Left operand:", left_name)
        print("Right operand:", right_name)

        print("Inputs:",[input.name for input in inputs])
        print("Add Instruction:",add_instruction)
        print("Output Instruction:",output_instruction)

        input_ports = ", ".join([f"%{inp.name}: {circt_type}" for inp in inputs])

        mlir = f"""
        hw.module @comb_adder({input_ports} , out: {circt_type}) {{
            %sum = comb.add {left_name}, {right_name} : {circt_type}
            hw.output %sum : {circt_type}
            }}
            """

        print(mlir)
        
            
        # return original btor2 program with no change for now
        return program