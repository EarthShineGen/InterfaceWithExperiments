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
  read_hepmc_cfg.py         read a .hepmc file with MCFileSource, or a
                            .hepmc3 file with MCFileSource3
  check_hepmc_roundtrip.py  assert CMSSW got back what the generator wrote
  run_read_validation.sh    the above over six generator configurations

  gensim_cfg.py             GEN-SIM: GEANT4 tracking the muons into CMS,
                            from either HepMC version
  check_gensim.py           assert GEANT took the right primaries, at the
                            right places, and made hits
  run_gensim.sh             generate, simulate and check, in one command

  run_chain.sh              the whole thing: HepMC 3 -> GEN-SIM -> DIGI-RAW
                            -> RECO, with the cosmics conditions
  check_reco.py             assert the cosmic reconstruction made tracks

  fragment_mcfilesource.py  the CMSSW fragment for the HepMC route, with the
                            customisation function for a cmsDriver cfg

  gridpack/                 the LHE route: gridpack build and GEN fragments
    earthshinegen_gridpack.sh          builds the tarball
    runcmsgrid_earthshinegen_generic.sh   parameter point passed at run time
    runcmsgrid_earthshinegen_specific.sh  parameter point baked into the card
    earthshinegen.py                   ExternalLHEProducer snippet
    run3_fragment.py                   the GEN fragment
```

## Two routes into CMSSW

|  | LHE, via a gridpack | HepMC, via MCFileSource |
|---|---|---|
| built by | `cmssw/gridpack/earthshinegen_gridpack.sh` | nothing: run the generator |
| read by | `ExternalLHEProducer` + `Pythia8HadronizerFilter` as a pass-through | `MCFileSource` |
| vertices | one per event, in comment lines a producer must be written to read | one per muon, natively |
| fits | central production, McM | driving it yourself |

Use the gridpack when you need the standard production machinery. Use HepMC
when the two muon entry points matter -- with `ms_model highland` they are
metres apart, and the single midpoint vertex stops being an approximation to
anything.

## Building a gridpack

The generator is staged into the tarball from its own repository, so the build
has to be told where that is:

```bash
export EARTHSHINEGEN=$HOME/EarthAsDM/EarthShineGen/EarthShineGen

cd cmssw/gridpack
./earthshinegen_gridpack.sh run3                          # generic
./earthshinegen_gridpack.sh run3 7000 0.23 1e-8 max core  # specific point
```

That writes `earthshinegen_gridpack_run3.tar.xz`, containing `runcmsgrid.sh`
and a flat `EarthShineGen/` tree. Nothing is compiled; the release is set up
only so the gridpack is built against the python and numpy the job will see.
A ten-event unit test runs before packing, in both output formats, so a broken
writer is caught here rather than in the job.

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
.../InterfaceWithExperiments/cmssw/run_chain.sh             # through RECO
```

## The full chain

`run_chain.sh` takes the generator all the way to RECO: generate HepMC 3,
GEN-SIM with `gensim_cfg.py`, then two stock `cmsDriver` steps for
`DIGI,L1,DIGI2RAW` and `RAW2DIGI,L1Reco,RECO`. It needs a release with
`MCFileSource3`; everything after GEN-SIM is release code with no
EarthShineGen-specific settings at all, because SIM hits are SIM hits.

Two choices in it are worth knowing about, and both follow from the signal
being cosmic-like rather than collision-like:

* **the cosmics GlobalTag**, `auto:phase1_2024_cosmics`
  (`140X_mcRun3_2024cosmics_realistic_deco_v14`), which is also the tag the
  analysis side uses, rather than `auto:phase1_2024_realistic`;
* **`--scenario cosmics`**, so that RECO runs the cosmic reconstruction --
  `ctfWithMaterialTracksP5`, `cosmicMuons`, `globalCosmicMuons`. A muon that
  enters from below has no beam spot, no primary vertex and no pt constraint,
  so the collision sequences have nothing to work with.

Note that `--scenario cosmics` also affects SIM, and there it currently must
not be used with HepMC 3; see Known issues.

## HepMC 2 or HepMC 3

The generator defaults to HepMC 3. Both versions now go all the way through.

`MCFileSource` (`IOMC/Input`) opens the file with `HepMC::IO_GenEvent` -- HepMC
**2** -- and produces `HepMCProduct`. `MCFileSource3`
([cms-sw/cmssw#51842](https://github.com/cms-sw/cmssw/pull/51842), same
package) reads HepMC 3 and produces `HepMC3Product` + `GenEventInfoProduct3`.
Both put their product at `('source', 'generator')`, so `hepmcVersion=2|3` is
the only difference in the cfgs.

GEANT takes either, which is the part that was previously thought to be
missing: `RunManagerMTWorker` consumes a `HepMCProduct` *and* a `HepMC3Product`
from the tag in `Generator.HepMCProductLabel`, and hands whichever it finds to
`Generator` or `Generator3`. Nothing in `g4SimHits_cfi.py` has to change.

Use HepMC 2 if the release predates #51842; it is the only reason to. Use
HepMC 3 otherwise -- it is what the generator writes without being asked, and
it needs no `firstLuminosityBlockForEachRun` incantation, because
`MCFileSource3` has `fillDescriptions` and `MCFileSource` does not.

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

**3. The A' has no production vertex.** The generator does not model the A'
flight -- it samples the decay point directly -- so writing a production vertex
would mean putting it at the decay point and giving the A' a zero-length flight
path. It is written as an incoming particle of its own decay vertex instead.
Do not read `|V_prod - V_dec|` as a measured flight distance; there is no such
vertex to measure against.

**4. The generator writes status 3, and it matters.** `Generator.cc` reads

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

With those settings, seed 20260907 gives 20 of 20 events with hits in the muon
system and 18 of 20 in the tracker; seed 20260909 gives 17 of 20 and 18 of 20.
Reaching the inner cylinder does not guarantee reaching a muon station, so the
muon-system rate is a property of the sample -- it comes out identically from
HepMC 2 and HepMC 3 -- and `check_gensim.py` prints it rather than requiring
all of them.

## Known issues

* [`docs/rpc-stepping.md`](docs/rpc-stepping.md) -- a small fraction of muons
  are killed by GEANT's step-count limit in the endcap chambers. Measured rate
  and a plan for making the limit configurable.

* **`NonBeamEvent` silently drops every primary in the HepMC 3 path.**
  `--scenario cosmics` pulls in `SimNOBEAM_cff`, which sets
  `g4SimHits.NonBeamEvent = True`. In `RunManagerMTWorker::generateEvent` the
  HepMC 2 branch then calls `nonCentralEvent2G4`, but in the HepMC 3 branch
  that call is commented out, so nothing is handed to GEANT and the job dies
  with

  ```
  RunManagerMTWorker::produce: event 1 with no G4PrimaryVertices
  ```

  `Generator3::nonCentralEvent2G4` is implemented; only the call site is
  missing. Until that is fixed upstream, run SIM without the cosmics scenario
  -- `gensim_cfg.py` does, and it selects the right primaries by the fiducial
  cuts instead -- and use `--scenario cosmics` only from DIGI onwards, which is
  what `run_chain.sh` does.
