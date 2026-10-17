import Verification.NumericSQLExpectedAuthority

open NumericSQLExpectedAuthority NumericSQLExpectedInstance
open NumericSQLDecisionEnvelope

def exampleJob : Job := ⟨"task-0", 1, 20, "sql-gap-binary64-1.0.0"⟩
def exampleGrant : Grant := ⟨10, "task-0", 1, "sql-gap-binary64-1.0.0",
  ⟨"context-0", ⟨1, 1, 1, .decimal⟩⟩⟩
example : Eligible (fun _ => true) exampleJob 10 exampleGrant := by decide
example : ¬ Eligible (fun _ => false) exampleJob 10 exampleGrant := by decide
example : ¬ Eligible (fun _ => true) exampleJob 11 exampleGrant := by decide
example : ¬ Eligible (fun _ => true) { exampleJob with executor := 10 } 10 exampleGrant := by decide
example : ¬ Eligible (fun _ => true) { exampleJob with task := "task-1" } 10 exampleGrant := by decide
example : ¬ Eligible (fun _ => true) { exampleJob with revision := 2 } 10 exampleGrant := by decide
example : ¬ Eligible (fun _ => true) { exampleJob with spec := "different" } 10 exampleGrant := by decide
example : runAuthorized (fun _ => true) exampleJob 10 none ByteArray.empty =
    ⟨"", .rejected .invalidContext⟩ := rfl
