import Verification.NumericSQLByteTransport
open NumericSQLByteTransport NumericSQLInstanceDecoder NumericSQLExpectedInstance
example : decodePacket 1 (packet .null) = .ok .null := by
  apply packet_complete
  · trivial
  · simp [packet, magic, encode]
example : decodePacket 1 (packet (.bool false)) = .ok (.bool false) := by
  apply packet_complete
  · trivial
  · simp [packet, magic, encode]
example : decodePacket 1 (packet (.bool true)) = .ok (.bool true) := by
  apply packet_complete
  · trivial
  · simp [packet, magic, encode]
example : decodePacket 1 [83,81,76,66,84,1,0,0] = .error "trailing" := by rfl
example : decodePacket 1 (packet (.string "é")) = .ok (.string "é") := by
  apply packet_complete
  · simp only [Admissible, utf8, Array.length_toList]
    decide +kernel
  · simp only [packet, magic, encode, NumericSQLByteTransport.text, word, List.length_append,
      List.length_cons, List.length_nil, utf8, Array.length_toList]
    decide +kernel
example : decodePacket 1 [83,81,76,66,84,1,4,0,2,192,128] = .error "utf8" := by rfl
example : readWord [255,255,0] = .ok (65535,[0]) := by rfl
example : decodePacket 0 (packet .null) = .error "resource_limit" := by
  simp [decodePacket, packet, magic, encode, decode, parse, bind, Except.bind]
example (n : Nat) (t : Tree) (ha : Admissible n t) (hb : (packet t).length ≤ 2*1024*1024) :
    decodePacket n (packet t) = .ok t := packet_complete n t ha hb
example (n : Nat) (e : ExpectedInstance) (b : ByteArray) (p : ParsedBoundCertificate)
    (h : acceptBytes n e b p = true) :
    ∃ t, b.data.toList = packet t ∧ decodeAST t = some e.input := by
  obtain ⟨t,hb,hd,_,_⟩ := accepted_bytes_rounding n e b p h
  exact ⟨t,hb,hd⟩
