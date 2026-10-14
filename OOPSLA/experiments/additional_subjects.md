# Additional QEC Software Subjects Framework (Gap 4)

Generated: 2026-10-11

## Subject Status Overview

### Stim + sinter + PyMatching (`stim_sinter_pymatching`)

- **Repo**: https://github.com/quantumlib/Stim

- **Pinned commit**: TODO

- **Description**: De facto standard: Stim for circuits, sinter for Monte Carlo, PyMatching for decoding

- **Status**: not_cloned

- **Components**:

  - `code`: Stim's stabilizer codes / custom code construction
  - `circuit`: Stim circuit generation (different from QUITS extractor)
  - `noise`: Stim's noise models (DEPOLARIZE, etc.)
  - `decoder`: PyMatching (MWPM) / sinter's internal decoders
  - `simulation`: sinter Monte Carlo sampling

- **Known hidden dependencies**:

  - Stim circuit construction reads noise parameters
  - sinter sampling depends on both circuit and decoder
  - PyMatching reads detector error model from Stim


### Deltakit (Google Quantum AI) (`deltakit`)

- **Repo**: https://github.com/quantumlib/deltakit

- **Pinned commit**: TODO

- **Description**: Google's QEC software stack with tile-based codes

- **Status**: not_cloned

- **Components**:

  - `code`: Tile-based stabilizer codes (surface, color, etc.)
  - `circuit`: Stim-based circuit construction
  - `noise`: Custom noise models
  - `decoder`: Internal decoders (MWPM, BP, etc.)

- **Known hidden dependencies**: None documented yet


### Tsim (AWS Braket / IonQ) (`tsim`)

- **Repo**: TODO

- **Pinned commit**: TODO

- **Description**: AWS Braket simulator for trapped ion QEC

- **Status**: not_available

- **Components**:

  - `code`: Trapped-ion specific codes
  - `circuit`: Native circuit construction
  - `noise`: Ion-specific noise models
  - `decoder`: Custom decoders

- **Known hidden dependencies**: None documented yet


### BP+OSD standalone decoder (`bp_osd_standalone`)

- **Repo**: https://github.com/quantumlib/bp_osd

- **Pinned commit**: TODO

- **Description**: Standalone BP+OSD decoder library

- **Status**: not_cloned

- **Components**:

  - `decoder`: BP+OSD implementation
  - `input`: Detector error model + syndrome

- **Known hidden dependencies**: None documented yet


### qec_code_sim (alternative simulator) (`qec_code_sim`)

- **Repo**: TODO

- **Pinned commit**: TODO

- **Description**: Alternative QEC simulator for cross-validation

- **Status**: not_available

- **Components**:

  - `code`: Multiple code families
  - `circuit`: Native circuit construction
  - `noise`: Standard noise models
  - `decoder`: Multiple decoders

- **Known hidden dependencies**: None documented yet


## Per-Subject Requirements

- Clone and pin repository at specific commit
- Identify component boundaries (code/circuit/noise/decoder/simulation)
- Map to semantic model: Spec, Component, Assembly
- Implement produce() functions returning real artifacts
- Extract declared read sets R(c) (static analysis or manual)
- Run hidden dependency audit (Theorem 3 probe)
- Run substitution experiments (Theorem 1 validation)
- Run physical impact experiments (LER, threshold, decoder ranking)
- Document any hidden dependencies found

## Infrastructure Needed

- Docker images for each subject (or conda environments)
- Shared evaluation script that works across subjects
- Unified artifact fingerprinting (stim circuit, DEM, etc.)
- Cross-subject comparison tables
