import Verification.NumericSQLControlDecoder
open NumericSQLControlDecoder NumericSQLInstanceDecoder NumericSQLExpectedInstance

def rat (n d : String) : Tree := .object
  [("numerator", .string n),("denominator", .string d)]
example : readNat "0002" = .ok 2 := by decide +kernel
example : readNat "-1" = .error "context_integer" := by decide +kernel
example : readRat (rat "2" "2") = .ok 1 := by decide +kernel
example : readRat (rat "0002" "0002") = .ok 1 := by decide +kernel
example : readRat (rat "1" "0") = .error "context_positive_domain" := by decide +kernel
example : readRat (rat "0" "1") = .error "context_positive_domain" := by decide +kernel
example : readRat (.object [("numerator",.number "1"),("denominator",.string "1")]) =
    .error "context_numerator" := by decide +kernel
example : readRat (.object [("numerator",.bool true),("denominator",.string "1")]) =
    .error "context_numerator" := by decide +kernel
example (t : Tree) (e : ExpectedInstance) (h : ContextRep t e) :
    decodeTree t = .ok e := decodeTree_complete t e h
example (bs : ByteArray) (e : ExpectedInstance) (h : decode bs = .ok e) :
    e.input.Positive := decoded_positive bs e h
example (control raw : ByteArray) (e : ExpectedInstance) (h : decode control = .ok e)
    (c : String) (other : SQLInstance)
    (f : NumericRoundingCertificates.FloatRepresentation NumericRoundingCertificates.binary64)
    (hne : other ≠ e.input) :
    runControl control raw ≠ ⟨c, .accepted other f⟩ :=
  different_instance_rejected control raw e h c other f hne
