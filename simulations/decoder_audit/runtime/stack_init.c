/* Resource configuration only, outside the arithmetic/AST theorem.
 * Lean's runtime may spawn initialization threads before module initializers.
 * Set the stack before lean_initialize, retaining the fixed 1 GiB process cap.
 */
typedef __SIZE_TYPE__ size_t;
extern void set_lean_stack(size_t) __asm__("_ZN4lean7lthread21set_thread_stack_sizeEm");
extern void __real_lean_initialize(void);
void __wrap_lean_initialize(void) {
    set_lean_stack(8 * 1024 * 1024);
    __real_lean_initialize();
}
