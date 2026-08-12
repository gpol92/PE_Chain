# PE_Chain
This repository contains an educational SystemVerilog digital circuit to make research on the HW development for AI

Example of usage (--warning let's you to suppress the info messages given by cocotb and Icarus Verilog)\
```python test_pe.py --warning```

Example of output
> [OK] Dot product value equal to expected (2)

Negative value test

```python test_pe.py --no-positive --warning```

Output
> [OK] Dot product value equal to expected (-2)

Zero value test

```python test_pe.py --zero --warning```

Output
> [OK] Dot product value equal to expected (0)

The cocotb harness instantiates the V0 multiplier (`v0_dut`), the V1
multiply-and-accumulate reference (`v1_dut`), and the actual implementation
from `pe.sv` (`pe_dut`). By default all three are checked:

```bash
python test_pe.py --warning
```

To check one version only:

```bash
python test_pe.py --version v0 --warning
python test_pe.py --version v1 --warning
python test_pe.py --version pe --warning
```
