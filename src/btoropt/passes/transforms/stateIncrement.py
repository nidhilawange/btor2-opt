from ...passes.genericpass import Pass
from ...program import Instruction, Next, Constd, Add


class StateIncrement(Pass):
    def __init__(self):
        super().__init__("state-increment")

    # check whether the instruction is a constant decimal instruction
    # checks whether operands[0] (holds datatype) and operands[1] (holds value of that operand in the instruction) match the datatype bit width of the state and actually holds 1
    def is_constant_one(self, instr, sort) -> bool:
        return (
        isinstance(instr, Constd) 
        and instr.operands[0] == sort 
        and instr.operands[1] == 1
        )

    # check whether state increment is actually occuring,
    # so we check the instruction that follows the current one (Next instruction)
    def is_incrementing(self, instr: Next) -> bool:
        # get the data type & bit-width and value of the state being updated all in the next instruction
        sort = instr.operands[0]
        state = instr.operands[1]
        # the operand to the right of the state:
        operand_right = instr.operands[2]

        # if that operand is an add instruction
        if not isinstance(operand_right, Add):
            return False
        # extract the lid reference to whichever previous line that holds the particular state and value of state which is one of the values you want to add to
        # extract this for the left-side operand to the addition and for the right-side operand to the addition
        # but either one of the extracted lids should reference a constant of 1 which is what is_constant_one checks
        left = operand_right.operands[1]
        right = operand_right.operands[2]

        # added after first check: could either be state + 1 or 1 + state
        return (
            (left == state and self._is_const_one(right, sort)) or
            (right == state and self._is_const_one(left, sort))
        )

    # now convert the state increment representation as checked above to the actual increment of a state
    def run(self, program: list[Instruction]) -> list[Instruction]:
        # empty list declaration of type Instruction for transformed program result
        transformed_program: list[Instruction] = program.copy()

        # need to find the line id of last instruction
        next_unused_lid = max(instr.lid for instr in program) + 1
        # then for every instruction in the parsed btor2 program
        for inst in program:
            # only transform those instruction objects that are state-update instructions
            if isinstance(inst, Next):
                if self.is_incrementing(inst):
                    transformed_program.append(inst)
                    continue

                state_sort = inst.operands[0]
                current_state = inst.operands[1]

                # create new btor2 constant representing 1 and keep incrementing lid
                const_one = Constd(next_unused_lid, state_sort, 1)
                next_unused_lid += 1

                # creates new btor2 add instruction with Add class and continue incrementing lid
                increment_expr = Add(next_unused_lid, state_sort, current_state, const_one)
                next_unused_lid += 1

                # so manually transform program to that constant 1 followed by the add instruction expression followed by Next() instruction object-transformed btor
                transformed_program.append(const_one)
                transformed_program.append(increment_expr)
                transformed_program.append(
                    Next(inst.lid, state_sort, current_state, increment_expr)
                )
                
            # enforce incrementing behavior in the BTOR2 transition system by constructing the exact IR lines needed for state + 1 and plugging them into the Next instruction.

        return transformed_program
