import Verification.NumericSQLASTTransport
open Lean NumericSQLASTTransport NumericSQLInstanceDecoder NumericSQLExpectedInstance

example : fromTransport 1 (.arr #[.str "null"]) = .ok Tree.null := by rfl
example : fromTransport 1 (.arr #[.str "bool", .bool false]) = .ok (.bool false) :=
  by rfl
example : fromTransport 1 (.arr #[.str "bool", .num 0]) = .error "tag_or_arity" :=
  by rfl
example : fromTransport 1 (.arr #[.str "number", .str "0"]) = .ok (.number "0") :=
  by rfl
example : encode (.string "0") ≠ encode (.number "0") := by
  intro h
  have := encode_injective h
  contradiction
example : fromTransport 0 (encode .null) = .error "resource_limit" := rfl
example : fromTransport 1 (encode (.number "1234567")) = .error "resource_limit" :=
  by rw [encode]; rfl
example : fromTransport 1 (encode (.array [.null])) = .error "resource_limit" :=
  by rw [encode]; rfl
example : fromTransport 2 (encode (.array [.null])) = .ok (.array [.null]) := by
  apply fromTransport_complete
  simp [Admissible]
example : fromTransport 2 (encode (.object [("A", .string "1"), ("A", .string "2")])) =
    .ok (.object [("A", .string "1"), ("A", .string "2")]) := by
  apply fromTransport_complete
  simp only [Admissible, List.length_cons, List.length_nil, List.mem_cons,
    List.not_mem_nil, or_false, forall_eq_or_imp, forall_eq]
  decide +kernel
example : field (.object [("A", .string "1"), ("A", .string "2")]) "A" = none :=
  by rfl
example (n : Nat) (t u : Tree) (h : fromTransport n (encode t) = .ok u) :
    stringField u "A" = stringField t "A" := by rw [preserves_tree n t u h]
example (n : Nat) (e : ExpectedInstance) (j : Json) (p : ParsedBoundCertificate)
    (h : acceptTransport n e j p = true) :
    ∃ t, j = encode t ∧ decodeAST t = some e.input := by
  obtain ⟨t,hj,hd,_,_⟩ := accepted_transport_rounding n e j p h
  exact ⟨t,hj,hd⟩
example (n : Nat) (e : ExpectedInstance) (t u : Tree) (x : SQLInstance)
    (p : ParsedBoundCertificate) (ht : fromTransport n (encode t) = .ok u)
    (hx : decodeAST t = some x) (hne : x ≠ e.input) :
    acceptTransport n e (encode t) p = false := transport_mismatch_rejected n e t u x p ht hx hne
