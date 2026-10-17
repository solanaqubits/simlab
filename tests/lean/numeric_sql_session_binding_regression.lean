import Verification.NumericSQLSessionBinding
open NumericSQLSessionBinding NumericSQLExpectedInstance NumericSQLDecisionEnvelope

def e : ExpectedInstance := ⟨"operator", ⟨1, 1, 1, .decimal⟩⟩
example : declaredLength [0, 1, 0, 0] = 65536 := by decide +kernel
example : checkFrame 1 [0, 0, 0, 1] ⟨#[42]⟩ = .ok ⟨#[42]⟩ := by decide +kernel
example : checkFrame 1 [0, 0, 0] ⟨#[]⟩ = .error .invalidInput := by decide +kernel
example : checkFrame 1 [0, 0, 0, 2] ⟨#[42, 43]⟩ = .error .resourceLimit := by decide +kernel
example : checkFrame 2 [0, 0, 0, 2] ⟨#[42]⟩ = .error .invalidInput := by decide +kernel
example : checkFrame 0 [0, 0, 0, 0] ⟨#[]⟩ = .ok ⟨#[]⟩ := by decide +kernel
example : (step ⟨e, 0⟩ ⟨#[]⟩).1.remaining = 0 := by decide +kernel
example : (step ⟨e, 1⟩ ⟨#[]⟩).1.remaining = 0 := by decide +kernel
example (s : Session) (bs : List ByteArray) : (advance s bs).expected = s.expected :=
  sequence_context s bs
example (s : Session) (raw : ByteArray) (h : s.remaining = 0) :
    (step s raw).2 = ⟨s.expected.contextId, .rejected .resourceLimit⟩ := exhausted s raw h
example (s : Session) (bs : List ByteArray) (raw : ByteArray) (c : String) (x : SQLInstance)
    (f : NumericRoundingCertificates.FloatRepresentation NumericRoundingCertificates.binary64)
    (hx : x ≠ s.expected.input) : (step (advance s bs) raw).2 ≠ ⟨c, .accepted x f⟩ :=
  different_instance_rejected s bs raw c x f hx
