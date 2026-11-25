 # ** BTOR-to-CIRCT Backend **

Overview: The backend translates parsed BTOR2 programs into CIRCT MLIR using CIRCT's core dialects.

The current implementation of this translator uses the following CIRCT Core dialects:
- HW
- Comb
- Seq
- Verif

The backend is implemented in emitCIRCTCore.py through the Btor2CirctTranslator class.

## ** Translator  Outline: `translate_btor_program()` **
1. Type Mappping
2. State information collection
3. Module interface construction
4. SSA Value Mapping
5. Instruction translation
6. Sequential State construction
7. Output Mapping

### Sort and Type Mapping

`construct_type_dict()` function maps each BTOR2 sort line ID to a corresponding CIRCT type, allowing subsequent translation functions to obtain the appropriate type without reconstructing it.

Bitvector sorts are represented using `signless` CIRCT integer types with widths equal to the original BTOR2 arrat declarations. Array sorts are represented with CIRCT HW array types for array values and the number of elements in the array are determined from the BTOR2 array's address width. For ex: an array with an 8-bit address and 32-bit elements has 256 elements, each a 32-bit value.

### Hardware Module Interface Construction

The CIRCT `hw.module` interface is constructed based on the input and output declarations in the BTOR program. The
`construct_input_ports()` function determines the CIRCT types of the input instructions using already-constructed type mapping. 

For state-based programs, the translator includes an implicit `clk` input of type `!seq.clock` because BTOR2 doesn't explicitly declare a clock signal. This is not necessary for combinational blocks.

The `construct_output_ports()` function determines the CIRCT types of BTOR2 output declarations from the instructions which reference the output. Both of these input and output interfaces are created before translating the individual instructions inside the hardware module.

### BTOR2-to-CIRCT SSA Value Mapping

The translator supports `line_value_dict` to connect the representations of unique line IDs in BTOR to its corresponding SSA values that the CIRCT operations produce, which future BTOR lines can reference. 

The function, `map_input_ports_values()` matches each BTOR input declaration with its corresponding module entry block argument. For state-based program, there is an implicit clock SSA value, which is stored separately in clock_value because it doesn't directly correspond to a specific BTOR line ID.

For each instruction, the CIRCT SSA values that result from the translation of that instruction are appended to the dictionary `line_value_dict` so that later instructions can obtain previously created operands by accessing their corresponding BTOR2 line ID.

The function, `map_output_values()` obtains the SSA values that a BTOR2 output actually references. The order of the SSA values retrieved is the same as the order of the output declarations in btor.


### Sequential and Memory Translation

## State translation *(bitvector representation)*

BTOR2 represents state-related behavior through `state`,`init`, and `next` instructions, which work together to establish a persistent state variable, its optional state value, and its next-state expression. The translator maintains these relationships in `state_dict`.

Bitvector states are represented using `seq.CompRegOp`. Since next-state expressions may reference current state values before their registers exist, the translator uses `BackedgeBuilder` to create temporary SSA values. Once the next-state logic and registers are constructed, `replace_all_uses_with()` replaces these temporary values with the actual register outputs, completing the sequential feedback connections.

## State translation *(array and memory representation)*

The BTOR2 array inputs represent the values supplied externally, while array states represent persistent storage. The translator therefore uses `hw.ArrayType` for normal inputs and `seq.HLMemOp` for array states. Memory depth and element type are determined by the corresponding BTOR2 array sort.

Unlike the bitvector states, high-level memories are instantiated directly without temporary backedges. Array reads are translated using the `hw.ArrayGetOp` for normal inputs while the `seq.ReadPortOp` operation is used with no read latency default for persistent memories.

## Memory state updates

BTOR2 follows functional array semantics, where `write` produces an updated array without modifying the original, and `next` determines the next memory state.

Since CIRCT uses explicit memory write ports, the translator defers the write translation until the sequential state construction. The direct memory updates use the operation `seq.WritePortOp` with a write latency of one default and an enabled write signal.

This difference avoids the functionl array from being incorrectly interpreted as persistent memory updates. 

### Testing

