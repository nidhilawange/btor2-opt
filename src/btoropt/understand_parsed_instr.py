# Nidhi Lawange
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