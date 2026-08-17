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

## TEST PE_CHAIN

In this paragraph I will give you examples of usage of the tool to do tests of a pe_chain with two PEs

```bash
python test_pe.py --passed --zero --pechain
python test_pe.py --passed --no-positive --pechain
python test_pe.py --passed --positive --pechain
```

### TEST PE_CHAIN with RAM addresses and access
```bash
python test_pe.py --pechain --arrays --v8
```
Example of output
> [OK] pechain_v8 data_addr=0 weight_addr=0 value equal to expected (68) \
> [OK] pechain_v8 data_addr=1 weight_addr=1 value equal to expected (-60)

Example with pe_chain and calculation with array element by element
```bash
python test_pe.py --pechain --arrays --v5 --positive
```

## FSM test

```bash
python test_pe.py --pechain --arrays --v9 
```

Example output

> [OK] V9 FSM completed with expected result (68) \
> [OK] V9 FSM completed with expected result (-60)

## TEST PE CHAIN COMMAND INTERFACE

```bash
python test_pe.py --pechain --arrays --v10
```

Example output

> [OK] V10 command completed without retrigger (68) \
> [OK] V10 command completed with retrigger attempt (-60)



