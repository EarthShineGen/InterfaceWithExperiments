# InterfaceWithExperiments

Everything experiment-specific for
[EarthShineGen](https://github.com/EarthShineGen/EarthShineGen).

The generator itself is deliberately experiment-neutral: it describes the
detector entirely through its parameter card (two coaxial cylinders and a
hand-off surface, every size a free parameter), depends on nothing but numpy
and scipy, and writes LHE, HepMC 2 and HepMC 3. Nothing in it imports, links
against or assumes CMSSW. Everything that *does* lives here.

Right now that means CMS. The layout has one directory per experiment, so
adding another does not disturb this one.

```
cmssw/
  read_hepmc_cfg.py         read a .hepmc file with MCFileSource
  check_hepmc_roundtrip.py  assert CMSSW got back what the generator wrote
  run_read_validation.sh    the above over six generator configurations

  gensim_cfg.py             GEN-SIM: GEANT4 tracking the muons into CMS
  check_gensim.py           assert GEANT took the right primaries, at the
                            right places, and made hits
  run_gensim.sh             generate, simulate and check, in one command

  fragment_mcfilesource.py  the CMSSW fragment for the HepMC route, with the
                            customisation function for a cmsDriver cfg
```

## Running

Nothing here has to be compiled and no CMSSW package has to be checked out:
every module used is a release plugin. Any CMSSW release with `MCFileSource`
works; the numbers quoted below were taken with `CMSSW_20_1_0_pre3`,
`el8_amd64_gcc14`.

```bash
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd <any CMSSW area>/src && cmsenv && cd -

export EARTHSHINEGEN=$HOME/EarthAsDM/EarthShineGen/EarthShineGen  # if not there
mkdir -p /tmp/esg && cd /tmp/esg

.../InterfaceWithExperiments/cmssw/run_read_validation.sh   # format level
.../InterfaceWithExperiments/cmssw/run_gensim.sh            # GEN-SIM level
```

## Why HepMC 2

`MCFileSource` (`IOMC/Input`) is the only file-based generator input source in
CMSSW, and it opens the file with `HepMC::IO_GenEvent` -- HepMC **2**. A
release-wide search finds no HepMC3 file reader; HepMC3 appears only inside
hadronizer interfaces (`Pythia8HepMC3Hadronizer` and friends), `HepMC3Product`
and Rivet. So `--hepmc_version 2` is what CMSSW reads and what these cfgs
expect. The generator's HepMC 3 output is for Rivet and everything else.

## Three things that are not obvious

**1. No vertex smearing.** The per-event vertex is the physics: the muons enter
from below, metres off the beamline, at two different points. `VtxSmeared`
would move both to the interaction point. So there is no smearing step and
`g4SimHits` reads the source product directly.

**2. `ApplyPCuts` stays on.** `SimG4Core/Generators/src/Generator.cc` computes

```cpp
fFiductialCuts = fPCuts || fPtransCut || fEtaCuts || fPhiCuts;
...
bool toBeAdded = !fFiductialCuts;
```

so turning *every* cut off -- the obvious move for particles that start 7.5 m
off-axis -- makes GEANT track the whole record, mock beams and dark photon
included, because the status-based selection is never reached. One cut has to
stay on. These cfgs keep `ApplyPCuts` and open its window to
`[0.04, 10^6] GeV` instead.

**3. The generator writes status 3, and it matters.** `Generator.cc` reads

| status | meaning |
|---|---|
| 1 | not decayed by the generator; GEANT tracks it |
| 2 | decayed, but GEANT still propagates it -- and if its end vertex is outside the beampipe (`RDecLenCut`, 2.9 cm) it is handed to GEANT with a predefined decay |
| 3 | decayed by the generator; GEANT must not propagate it |
| 4 | beam particle |

The dark photon and the muons-as-produced sit at the decay point, a kilometre
underground, and their end vertices are 7.5 m out. With status 2 GEANT would
start tracking them down there. They are written as status 3, which is also
simply what is true: the generator has already done that propagation.

## Choosing a sample for GEN-SIM

EarthShineGen's default `require_hit detector` only asks that the muon reach
the hand-off surface -- which by default *is* the detector's own outer
cylinder, so the requirement is satisfied by construction and most such muons
clip the outside and travel on up without entering CMS. For a GEN-SIM sample
ask for the inner cylinder and shorten the surface to where CMS actually ends:

```
--require_hit inner_detector --require_both_muons 1 --detector_half_length 11
```

With those settings, 20 of 20 events leave hits in the muon system and 18 of 20
in the tracker.

## Known issues

* [`docs/rpc-stepping.md`](docs/rpc-stepping.md) -- a small fraction of muons
  are killed by GEANT's step-count limit in the endcap chambers. Measured rate
  and a plan for making the limit configurable.
