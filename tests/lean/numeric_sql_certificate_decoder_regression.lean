import Verification.NumericSQLCertificateDecoder
open NumericSQLCertificateDecoder NumericSQLInstanceDecoder NumericSQLExpectedInstance

def ratNode (n d : String) : Tree :=
  .object [("numerator",.string n),("denominator",.string d)]
example : readRat (ratNode "1" "2") = .ok (1/2) := by decide +kernel
example : readRat (ratNode "2" "4") = .error "rational_representation" := by decide +kernel
example : readRat (ratNode "1" "0") = .error "rational_denominator" := by decide +kernel
example : readRat (ratNode "1" "-1") = .error "rational_denominator" := by decide +kernel
example : resultBits NumericRoundingCertificates.positiveZero = "0000000000000000" := by
  decide +kernel
example : readResult "7ff8000000000000" = .error "nan_encoding" := by decide +kernel
example (e : ExpectedInstance) (t : Tree) (p : ParsedBoundCertificate)
    (h : validateTree e t = .ok p) : p.actual = e.input := validated_actual_eq e t p h
example (e : ExpectedInstance) (bs : ByteArray) (p : ParsedBoundCertificate)
    (h : validate e bs = .ok p) : ∃ t, CertificateRep t p ∧ ASTRep t e.input := by
  obtain ⟨t,_,hc,hi,_,_⟩ := validated_original_bytes e bs p h
  exact ⟨t,hc,hi⟩
