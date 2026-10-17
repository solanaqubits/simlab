import Verification.NumericSQLStreamReader
open NumericSQLStreamReader
example : feed ⟨2, [1]⟩ [2] = .ok ⟨2, [1, 2]⟩ := by decide +kernel
example : feed ⟨2, [1]⟩ [] = .error .invalidChunk := by decide +kernel
example : feed ⟨2, [1]⟩ [2, 3] = .error .invalidChunk := by decide +kernel
example : feed ⟨0, [1]⟩ [2] = .error .invalidChunk := by decide +kernel
example : initial 0 = .done [] := by decide +kernel
example : replay true (initial 2) [.data [0], .data [1]] = .done [0, 1] := by decide +kernel
example : replay true (initial 2) [.eof, .data [0, 1]] = .failed .eof := by decide +kernel
example : replay false (initial 2) [.eof] = .failed .truncated := by decide +kernel
example : replay true (initial 2) [.data [0], .eof] = .failed .truncated := by decide +kernel
example : replay true (initial 2) [.data [], .data [0, 1]] = .failed .invalidChunk :=
  by decide +kernel
example (c : Bool) (n : Nat) (a b : List Bytes)
    (ha : ∀ x ∈ a, x ≠ []) (hb : ∀ x ∈ b, x ≠ [])
    (he : a.flatten = b.flatten) (hl : a.flatten.length = n) :
    replay c (initial n) (a.map Event.data) = replay c (initial n) (b.map Event.data) :=
  fragmentation_independent c n a b ha hb he hl
example (c : Bool) (n : Nat) (es : List Event) (b : Bytes)
    (h : replay c (initial n) es = .done b) : b.length = n ∧
    ∃ tail, (es.map eventBytes).flatten = b ++ tail := completed_exact c n es b h
