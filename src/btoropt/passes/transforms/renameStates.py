# Example pass: Rename all states to reg_0 to reg_n where "state" keyword shows in parsed btor2 file

# Nidhi Lawange

from ..genericpass import Pass
from ...program import Instruction, State

class RenameStates(Pass):
    def __init__(self):
        super().__init__("rename-states")

    def run(self, p: list[Instruction]) -> list[Instruction]:
        i = 0
        res = []
        for inst in p:
            if isinstance(inst, State):
                res.append(State(inst.lid, inst.operands[0], f"state_{i}"))
                i += 1
            else:
                res.append(inst)
        return res