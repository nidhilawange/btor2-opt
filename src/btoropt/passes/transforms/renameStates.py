##########################################################################
# Example pass: Rename all states to reg_0 to reg_n where "state"
# keyword shows in parsed btor2 file
#
# Copyright (C) 2026  Nidhi Lawange
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
########################################################################

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