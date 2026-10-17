import Verification.NumericSQLDecisionEnvelope
open NumericSQLDecisionEnvelope NumericSQLExpectedInstance NumericSQLInstanceDecoder
open NumericRoundingCertificates
example (raw : ByteArray) : run none raw = ⟨"", .rejected .invalidContext⟩ := rfl
example : classify "indeterminate" = .indeterminate := by decide +kernel
example : classify "resource_limit" = .resourceLimit := by decide +kernel
example (c : String) (why : Refusal) :
    field (toTree ⟨c, .rejected why⟩) "result_bits" = some .null :=
  (refusal_has_no_result c why).2
example (r : Envelope) (wire : NumericSQLByteTransport.Bytes) (h : emit r = .ok wire) :
    NumericSQLByteTransport.decodePacket 12 wire = .ok (toTree r) := emit_preserves r wire h
example (e : ExpectedInstance) (raw : ByteArray) (wire : NumericSQLByteTransport.Bytes)
    (c : String) (x : SQLInstance) (f : FloatRepresentation binary64)
    (h : consume (some e) raw wire = some ⟨c, .accepted x f⟩) :
    x = e.input ∧ NumericRealRounding.realRound binary64 e.input.gap = f := by
  obtain ⟨_,hx,hf,_⟩ := consumed_accepted_sound e raw wire c x f h
  exact ⟨hx,hf⟩
example (e : Option ExpectedInstance) (raw : ByteArray)
    (wire : NumericSQLByteTransport.Bytes) (h : emit (run e raw) ≠ .ok wire) :
    consume e raw wire = none := output_tampering_rejected e raw wire h
