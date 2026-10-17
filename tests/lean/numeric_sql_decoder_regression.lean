import Verification.NumericSQLInstanceDecoder
open NumericSQLDecimalDecoder NumericSQLInstanceDecoder NumericSQLExpectedInstance

example : decode "1.25".toList = some (5 / 4) := by decide +kernel
example : decode "+01.000e+0".toList = some 1 := by decide +kernel
example : decode ".1".toList = some (1 / 10) := by decide +kernel
example : decode "1e".toList = none := by decide +kernel
example : decode "1_0".toList = none := by decide +kernel
example : decodeNumber .decimal "0" = none := by decide +kernel
example : decodeNumber .decimal "-1" = none := by decide +kernel
example : decodeSource ⟨"1", "1", "1", .decimal⟩ =
    some ⟨1, 1, 1, .decimal⟩ := by decide +kernel
example : field (.object [("A", .string "1"), ("A", .string "1")]) "A" = none :=
  by decide +kernel
example : stringField (.object [("A", .number "1")]) "A" = none := by decide +kernel
example : stringField (.object [("A", .bool true)]) "A" = none := by decide +kernel
example : decodeAST .null = none := by decide +kernel
example (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : acceptDecoded e t p = true) : decodeAST t = some e.input :=
  (accepted_decoded_rounding e t p h).1
example (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (x : SQLInstance) (h : decodeAST t = some x) (hn : x ≠ e.input) :
    acceptDecoded e t p = false := decoded_mismatch_rejected e t p x h hn
example (sem : InputSemantics) (q v : ℚ) (h : SemanticsRep sem q v) :
    convert sem q = some v := convert_complete sem q v h
