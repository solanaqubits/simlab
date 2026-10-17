import Verification.NumericSQLJSONParser
open NumericSQLJSONGrammar NumericSQLJSONParser NumericSQLInstanceDecoder NumericSQLExpectedInstance
example : check 2 (.number ['0','1']) = false := by decide +kernel
example : check 2 (.number ['-','0']) = true := by decide +kernel
example : integerValue ['-','0'] = "0" := by rfl
example : check 2 (.string [.unicode ['D','8','0','0']]) = false := by decide +kernel
example : check 2 (.string [.pair ['D','8','3','4'] ['D','D','1','E']]) = true := by decide +kernel
example : check 3 (.object [] [([], [.literal 'A'], [], .null),
    ([], [.unicode ['0','0','4','1']], [], .null)]) = false := by decide +kernel
example (cs : Chars) (h : cs.length ≤ 4096)
    (hg : ∀ c ∈ cs, (JUnit.literal c).Valid)
    (hb : (String.ofList ('"'::(cs ++ ['"']))).toUTF8.size ≤ 262144) :
    decode (String.ofList ('"'::(cs ++ ['"']))).toUTF8 = .ok (.string (String.ofList cs)) :=
  decode_literal_complete cs h hg hb
example (e : ExpectedInstance) (bs : ByteArray) (p : ParsedBoundCertificate)
    (h : acceptJSON e bs p = true) : ∃ t, Represents 64 bs.data.toList t ∧ ASTRep t e.input := by
  obtain ⟨t,hr,ha,_,_⟩ := accepted_json_rounding e bs p h
  exact ⟨t,hr,ha⟩
example : certify 2 "true".toUTF8.data.toList (.bool false) = none := by
  simp [certify, check, render]
  decide +kernel
