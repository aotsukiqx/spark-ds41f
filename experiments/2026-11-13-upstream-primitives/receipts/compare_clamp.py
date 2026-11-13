"""Cross-variant comparison for the clamp bench: bit-exactness and NaN rule."""
import torch

mid = torch.load("/out/mid.pt")
new = torch.load("/out/new.pt")
old = torch.load("/out/old.pt")

same_inputs = (torch.equal(mid["x"], new["x"]) and torch.equal(mid["psum"], new["psum"])
               and torch.equal(mid["w"], new["w"]))
print(f"inputs identical across variants: {same_inputs}")
assert same_inputs

bitexact = torch.equal(mid["out"], new["out"]) and torch.equal(mid["out_sf"], new["out_sf"])
print(f"mid (Select) vs new (clamp_symmetric) outputs bit-exact: {bitexact}")

diff = (mid["out"] != new["out"]).sum().item()
print(f"differing elements: {diff} of {mid['out'].numel()}")

print("timing (us/iter):")
rows = sorted(mid["us"])
print(f"{'rows':>6} {'old':>9} {'mid':>9} {'new':>9} {'new/mid':>8}")
for r in rows:
    o, m, n = old["us"][r], mid["us"][r], new["us"][r]
    print(f"{r:>6} {o:>9.2f} {m:>9.2f} {n:>9.2f} {n / m:>8.4f}")

# The NaN rule itself was probed per variant and printed by bench_clamp.py;
# this script only asserts the finite-path equivalence that serving relies on.
assert bitexact, "clamp_symmetric changed finite-input results"
print("PASS: finite path bit-identical")
