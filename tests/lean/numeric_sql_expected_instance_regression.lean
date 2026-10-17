import Verification.NumericSQLExpectedInstance

open NumericSQLExpectedInstance NumericSQLIntervalBounds NumericRoundingCertificates
open NumericRealRounding
open NumericCertificateDigestBridge

def j0 : SQLInstance := ⟨1, 1, 1, .decimal⟩
def j1 : SQLInstance := ⟨1, 1, 4, .decimal⟩
def j2 : SQLInstance := ⟨9, 4, 3/2, .decimal⟩
def e0 : ExpectedInstance := ⟨"operator/J0", j0⟩
def e1 : ExpectedInstance := ⟨"operator/J1", j1⟩
def e2 : ExpectedInstance := ⟨"operator/J2", j2⟩
def root1 : RatInterval := ⟨1,1,by decide⟩
def p0 : ParsedBoundCertificate := ⟨j0,root1,positiveZero⟩
def f225 : FloatRepresentation binary64 := ⟨false,⟨4612248968380809216,by decide +kernel⟩⟩
def p1 : ParsedBoundCertificate := ⟨j1,root1,f225⟩
def p2 : ParsedBoundCertificate := ⟨j2,⟨6,6,by decide⟩,positiveZero⟩
example : accept e0 p0 = true := by decide +kernel
example : accept e1 p1 = true := by decide +kernel
example : accept e2 p2 = true := by decide +kernel
example : accept e0 p1 = false := by decide +kernel
-- Same +0 result does not establish the intended mathematical instance.
example : p0.result = p2.result ∧ accept e0 p2 = false := by decide +kernel
example : acceptWithContext none p0 = false := rfl
example : realRound binary64 e0.input.gap = positiveZero :=
  accepted_expected_rounding e0 p0 (by decide +kernel)
example : accept e0 { p0 with result := negativeZero } = false := by decide +kernel
example : accept e0 { p0 with actual := { j0 with semantics := .binary64 } } = false := by
  decide +kernel
example : accept e0 { p0 with root := ⟨0,0,by decide⟩ } = false := by decide +kernel
example : accept e0 { p0 with actual := { j0 with A := 2 } } = false := by decide +kernel
example : accept e0 { p0 with actual := { j0 with B := 2 } } = false := by decide +kernel
example : accept e0 { p0 with actual := { j0 with I := 2 } } = false := by decide +kernel
-- Equivalent rational representation is the same value in Lean, not a byte test.
example : accept e0 { p0 with actual := ⟨2/2,3/3,4/4,.decimal⟩ } = true := by decide +kernel
-- The bytes cannot choose a new expected instance, even for a constant parser.
example (digest : DigestFunction) (bytes : List UInt8) :
    validateBoundPayload e0 digest (fun _ => some p1) (digest bytes) bytes = none := by
  simp [validateBoundPayload, show accept e0 p1 = false by decide +kernel]
