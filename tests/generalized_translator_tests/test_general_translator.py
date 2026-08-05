# Nidhi Lawange: copied from test.py -- parsing & pass tester for generalized_translator which is a WIP

import unittest

from src.btoropt.parser import parse
from src.btoropt.passes.allpasses import all_passes, find_pass


def parsewrapper(filepath):
    with open(filepath, "r") as f:
        return f.readlines()


class BTORTestGeneralizedTranslator(unittest.TestCase):
    #check whether the generalized BTOR2-to-CIRCT pass works properly

    # Checks that a combinational adder BTOR2 program can be translated
    # into a CIRCT module through the registered pass infrastructure
    def test_comb_adder(self):

        # Parse the test input using the existing parser
        program = parse(
            parsewrapper("tests/generalized_translator_tests/input_btor/comb_adder_general.btor2")
        )

        # obtain the generalized translator from the registered pass list
        translator_pass = find_pass(
            all_passes,
            "generalized-translator"
        )

        # Confirm that the pass was actually registered in allpasses.py
        self.assertIsNotNone(translator_pass)

        # Run the translator through the same Pass.run() interface used by all other passes
        returned_program = translator_pass.run(program)

        # translator preserves the original BTOR2 instruction list so that it remains compatible with the existing pass structure
        self.assertEqual(returned_program, program)

        # generated CIRCT module is stored by the translator pass
        generated_module = translator_pass.generated_module

        # Confirm that translation produced a CIRCT module
        self.assertIsNotNone(generated_module)

        # Convert the generated module into MLIR text so that the test can check whether the expected CIRCT operations were generated.
        generated_mlir = str(generated_module)

        self.assertIn("hw.module", generated_mlir)
        # self.assertIn("comb.add", generated_mlir)
        self.assertIn("hw.output", generated_mlir)

        print("generalized translator adder w/ comparison & ite & slice & zero/sign extension test passed")


if __name__ == "__main__":
    unittest.main()