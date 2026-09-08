# The endcap step limit, and making it configurable

## What happens

A small fraction of EarthShineGen muons are killed part-way through GEANT4
tracking:

```
Track #1 mu- E(MeV)=1.09773e+06 Nstep=20001 is killed due to limit on number
  of steps;  PV:csc:ME12SpaceDivision_7 at (-2810.24,2484.6,6846.73)
  StepLen(mm)=0.442272
```

The killed track stops there. Its hits up to that point are kept, so the event
is not lost, but it is truncated: a muon that should have crossed the endcap
and left hits in the outer stations simply stops.

## Measured, not guessed

100 events (200 muons), `CMSSW_20_1_0_pre3`, `el8_amd64_gcc14`, seed 4242,
default EarthShineGen acceptance (`require_hit detector`), one thread:

| `MaxNumberOfSteps` | tracks killed | CPU for 100 events |
|---|---|---|
| 20000 (release default) | 3 of 200 (1.5%) | 68.6 s |
| 200000 | 0 of 200 | 71.0 s |

Raising the limit by a factor of ten removes the truncation entirely and costs
**3.5% CPU** on this sample.

Where they die, and how:

| volume | track | energy | step length at the kill |
|---|---|---|---|
| `csc:ME12SpaceDivision_7` | mu− | 1.10 TeV | 0.44 mm |
| `csc:ME12AlumFrame_1` | mu+ | 277 GeV | 0.11 mm |
| `rpcf:RTXUR_11` | mu− | 168 GeV | 0.96 mm |

All three are ME1/2-region endcap volumes, all three are high-energy muons, and
all three are taking sub-millimetre steps. That is the signature of grazing
incidence through a thin layered structure: the muon is spending its step
budget on geometry boundaries, not on physics.

It is also specific to how the sample was selected. The same 100-event exercise
with `--require_hit inner_detector --require_both_muons 1
--detector_half_length 11` -- the settings `run_gensim.sh` uses, which point
the muons at the middle of the detector rather than letting them graze the
outside -- gives **0 kills of 200** at the release default.

So: this is not an RPC bug, and despite the first example it is not really an
RPC issue at all. It is what happens when muons arrive nearly parallel to the
endcap disks, which is exactly the geometry this signal produces and exactly
what a collider-tuned default was not chosen for.

## It is already configurable

`SteppingAction.MaxNumberOfSteps` is a plain tracked `cms.int32` in
`SimG4Core/Application/python/g4SimHits_cfi.py`, read once in
`SteppingAction.cc` (and `Phase2SteppingAction.cc`):

```python
process.g4SimHits.SteppingAction.MaxNumberOfSteps = cms.int32(200000)
```

`gensim_cfg.py` in this repository exposes it as `maxSteps=`, so no CMSSW
change is needed to raise it:

```bash
cmsRun gensim_cfg.py inputFiles=file:events.hepmc maxSteps=200000
```

Anything below is only worth doing if a global raise turns out to be too
expensive on a real production sample, which on the evidence above it is not.

## Plan

### Step 0 -- done

Expose `maxSteps` in `gensim_cfg.py`; measure the kill rate and the CPU cost
(the table above). **Recommendation: set `maxSteps=200000` for EarthShineGen
GEN-SIM samples and stop here** unless step 1 turns up something worse.

### Step 1 -- confirm the mechanism before doing anything structural

The 3.5% figure is from 100 events with two muons each. Before proposing a
CMSSW change, check that the cost stays flat and that the steps really are
geometry-limited rather than a transport pathology:

* Run 1000 events at both limits and confirm the CPU ratio holds. If a
  handful of tracks are looping rather than crossing, the tail will show up as
  a few very slow events rather than a uniform 3.5%.
* Turn on `process.g4SimHits.SteppingAction.Verbosity` / `VerboseTracks` for
  one of the killed track ids and look at the step list: a muon crossing the
  endcap should show a monotonic progression in |z|. A track whose position
  barely changes over thousands of steps is stuck on a boundary, which is a
  geometry or transport bug and needs a different fix entirely -- raising the
  limit would just make it slower.
* Compare hit multiplicity per event at the two limits, to quantify what the
  truncation was actually costing in the muon system.

### Step 2 -- only if a global raise proves too expensive

A global `MaxNumberOfSteps` applies to every track in every volume, so raising
it protects pathological tracks elsewhere too. If that becomes a measurable
cost in a large production, the wanted thing is a per-region limit.

There is an exact precedent to copy in the same PSet. `common_maximum_time`
already pairs a global value with a region-keyed override list:

```python
MaxTrackTime  = cms.double(500.0),   # ns, the global value
MaxTimeNames  = cms.vstring(),       # region names
MaxTrackTimes = cms.vdouble(),       # ns, one per name
```

The change would mirror it:

```python
MaxNumberOfSteps      = cms.int32(20000),   # global, unchanged
MaxNumberOfStepsNames = cms.vstring(),      # region names
MaxNumberOfStepsList  = cms.vint32(),       # one per name
```

with `SteppingAction` resolving the region at construction the way the time
limits already are, and falling back to the global value. Empty vectors
reproduce today's behaviour exactly, which is what makes it reviewable.

Files: `SimG4Core/Application/src/SteppingAction.cc` +
`interface/SteppingAction.h`, the same pair for `Phase2SteppingAction`, and the
defaults in `python/g4SimHits_cfi.py`.

Note that the region to name is the muon endcap region, not "the RPCs" -- the
kills are spread over CSC and RPC volumes alike, and what they have in common
is the incidence angle, not the subdetector.

### Step 3 -- upstream it, or do not

A CMSSW pull request is only worth the review effort if step 1 shows the global
raise is genuinely costly. Otherwise the right outcome is a documented setting
in this repository's cfgs and nothing in CMSSW at all. Say so in the PR
description if it is opened: a change that exists only to serve one analysis'
unusual geometry is a maintenance cost for everyone else.

## Acceptance criteria

1. No `killed due to limit on number of steps` in a 1000-event GEN-SIM sample
   at the chosen setting.
2. The CPU cost of the chosen setting measured on that sample, not the
   100-event one.
3. Hit multiplicity in the muon system unchanged or higher, and the difference
   attributed.
4. If step 2 is done: empty override vectors reproduce the current sample bit
   for bit.
