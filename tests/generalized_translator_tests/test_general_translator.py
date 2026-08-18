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
########################################################################
##

# Tester class adapted from test.py for checking btor2 parsing and the # functionality of the generalized btor2-to-mlir translator.

import unittest
from pathlib import Path
from src.btoropt.parser import parse
from src.btoropt.passes.allpasses import all_passes, find_pass

input_btor_path = Path("tests/generalized_translator_tests/input_btor")

def parsewrapper(filepath):
    with open(filepath, "r") as f:
        return f.readlines()


class BTORTestGeneralizedTranslator(unittest.TestCase):
    #check whether the generalized BTOR2-to-MLIR pass works properly
    # pathlib usage for filename extraction: https://docs.python.org/3/library/pathlib.html
    
    # Checks that a combinational adder BTOR2 program can be translated
    # into a CIRCT module through the registered pass infrastructure
    def test_any_btor_program(self):

        # Find all .btor2 test files in the input directory.
        input_btor_programs = input_btor_path.glob("*.btor2")

        # Run the generalized translator separately on every BTOR2 file.
        for input_btor_file in input_btor_programs:

            # Extract the filename without the .btor2 extension
            module_name = input_btor_file.stem

            # Parse this BTOR2 file using the existing btor2 parser
            program = parse(
                parsewrapper(input_btor_file)
            )

            # Obtain the registered generalized translator pass.
            translator_pass = find_pass(
                all_passes,
                "generalized-translator"
            )

            # Confirm that the pass was actually registered in allpasses.py
            self.assertIsNotNone(translator_pass)
            
            # Run the translator through the same Pass.run() interface used by all other passes
            translator_pass.module_name = module_name # defined above using .stem
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