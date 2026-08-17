##########################################################################
# Utility for inspecting and understanding the internal representation # of parsed BTOR2 instructions.
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

from btoropt.parser import parse

def understand_instruction(inst):
    print("-" * 70)
    print("Python class:", type(inst).__name__)
    print("btor line ID:", inst.lid)
    print("btor operaiton", inst.inst)
    print("Attributes:", vars(inst))

    print("Operands:")

    for index, operand in enumerate(inst.operands):
        if hasattr(operand, "lid"):
            print(
                f"operands[{index}] = "
                f"{type(operand).__name__}"
                f"(lid={operand.lid}, inst={operand.inst})"
            )
        else:
            print(
                f"operands[{index}] = "
                f"{operand!r}"
            )


def main():
    with open("comb_adder_extrainput.btor2", "r") as file:
        program = parse(file.readlines())

    for instruction in program:
        understand_instruction(instruction)


if __name__ == "__main__":
    main()