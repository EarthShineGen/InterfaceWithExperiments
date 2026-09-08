"""GEN-SIM from an EarthShineGen HepMC file.

    cmsRun gensim_cfg.py inputFiles=file:events.hepmc \\
        outputFile=gensim.root maxEvents=20

EarthShineGen (https://github.com/EarthShineGen/EarthShineGen) writes a dark
Earthshine signal: a dark photon decays in the rock under the detector and the
two muons travel up through the overburden and enter the detector from below.
It writes HepMC 2, which `MCFileSource` reads, and the record has one
production vertex per muon at the point where that muon crosses the hand-off
surface -- by default the detector's own outer cylinder.

Three things about this cfg differ from a standard GEN-SIM and all three are
forced by that geometry:

1.  There is no VtxSmeared step and `g4SimHits` reads the source product
    directly.  The per-event vertex is the physics here; the beamspot smearing
    would move both muons to the interaction point.

2.  The muons enter ~7.5 m from the beamline, so the eta cut in SimG4Core's
    Generator is switched off.  It is written for particles that start inside
    the beampipe and only ever fires on vertices with r < RDecLenCut, so
    leaving it on would in fact be harmless -- it is off to make the intent
    explicit, not to fix a failure.

3.  ApplyPCuts stays ON, with the momentum window opened up instead.  That is
    not fussiness: SimG4Core's Generator computes
    `fFiductialCuts = fPCuts || fPtransCut || fEtaCuts || fPhiCuts` and starts
    every particle from `toBeAdded = !fFiductialCuts`, so switching every cut
    off makes GEANT track *everything* in the record, including the mock beam
    particles and the dark photon.  One cut has to stay on for the status-based
    selection to be reached at all.

The generator record itself is built to cooperate: the A' and the muons as
produced carry status 3 (decayed by the generator, do not propagate), so the
only primaries GEANT sees are the two status-1 muons at the hand-off surface.
Were they status 2, SimG4Core would hand GEANT a muon starting a kilometre
underground, because its end vertex is outside the beampipe.
"""

import FWCore.ParameterSet.Config as cms
from FWCore.ParameterSet.VarParsing import VarParsing
from Configuration.Eras.Era_Run3_2024_cff import Run3_2024

options = VarParsing('analysis')
options.setDefault('inputFiles', ['file:events.hepmc'])
options.setDefault('outputFile', 'earthshinegen_gensim.root')
options.setDefault('maxEvents', 20)
options.register('maxSteps', 20000,
                 VarParsing.multiplicity.singleton, VarParsing.varType.int,
                 'GEANT step-count limit per track (SteppingAction.'
                 'MaxNumberOfSteps).  The release default is 20000, at which '
                 'a small fraction of these muons are killed in the endcap '
                 'chambers; see docs/rpc-stepping.md.')
options.parseArguments()

process = cms.Process('SIM', Run3_2024)

process.load('Configuration.StandardSequences.Services_cff')
process.load('SimGeneral.HepPDTESSource.pythiapdt_cfi')
process.load('FWCore.MessageService.MessageLogger_cfi')
process.load('Configuration.EventContent.EventContent_cff')
process.load('SimGeneral.MixingModule.mixNoPU_cfi')
process.load('Configuration.StandardSequences.GeometrySimDB_cff')
process.load('Configuration.StandardSequences.MagneticField_cff')
process.load('Configuration.StandardSequences.SimIdeal_cff')
process.load('Configuration.StandardSequences.EndOfProcess_cff')
process.load('Configuration.StandardSequences.FrontierConditions_GlobalTag_cff')

from Configuration.AlCa.GlobalTag import GlobalTag
process.GlobalTag = GlobalTag(process.GlobalTag,
                              'auto:phase1_2024_realistic', '')
if hasattr(process, "XMLFromDBSource"):
    process.XMLFromDBSource.label = "Extended"
if hasattr(process, "DDDetectorESProducerFromDB"):
    process.DDDetectorESProducerFromDB.label = "Extended"

process.source = cms.Source(
    "MCFileSource",
    fileNames=cms.untracked.vstring(options.inputFiles),
    # MCFileSource has no fillDescriptions, so this ProducerSourceBase
    # parameter has to be given by hand; it has no default.
    firstLuminosityBlockForEachRun=cms.untracked.VLuminosityBlockID(),
)
process.maxEvents = cms.untracked.PSet(
    input=cms.untracked.int32(options.maxEvents))

process.MessageLogger.cerr.FwkReport.reportEvery = 1

# --- the three points from the docstring -----------------------------------
GENERATOR_PRODUCT = cms.InputTag('source', 'generator')
process.g4SimHits.HepMCProductLabel = GENERATOR_PRODUCT
process.g4SimHits.Generator.HepMCProductLabel = GENERATOR_PRODUCT
process.g4SimHits.Generator.ApplyPCuts = cms.bool(True)
process.g4SimHits.Generator.MinPCut = cms.double(0.04)
process.g4SimHits.Generator.MaxPCut = cms.double(1.0e6)
process.g4SimHits.Generator.ApplyEtaCuts = cms.bool(False)
process.g4SimHits.Generator.ApplyPhiCuts = cms.bool(False)
process.g4SimHits.Generator.ApplyPtransCut = cms.bool(False)

# The Run3 era turns on the PPS beamline transport, whose producer only exists
# in the SimExtended sequence.  There are no forward protons in this signal.
process.g4SimHits.LHCTransport = cms.bool(False)

# GEANT tracks two muons and nothing else, so the default 500 ns track-time
# budget is generous; the reason it is set at all is that a misconfigured
# record (status 2 intermediates, say) shows up as an event that never
# finishes rather than as an error.
process.g4SimHits.StackingAction.MaxTrackTime = cms.double(500.0)

# The step-count limit.  Exposed because these muons arrive at grazing
# incidence on the endcap chambers, where a few per cent of them run out of
# steps before they run out of detector; docs/rpc-stepping.md has the measured
# rate and what raising this costs.
process.g4SimHits.SteppingAction.MaxNumberOfSteps = cms.int32(options.maxSteps)

process.output = cms.OutputModule(
    "PoolOutputModule",
    fileName=cms.untracked.string(options.outputFile),
    dataset=cms.untracked.PSet(dataTier=cms.untracked.string('GEN-SIM'),
                               filterName=cms.untracked.string('')),
    outputCommands=cms.untracked.vstring(
        'drop *',
        'keep *_source_*_*',
        'keep *_g4SimHits_*_*',
    ),
    splitLevel=cms.untracked.int32(0),
)

process.simulation_step = cms.Path(process.psim)
process.endjob_step = cms.EndPath(process.endOfProcess)
process.output_step = cms.EndPath(process.output)
process.schedule = cms.Schedule(process.simulation_step,
                                process.endjob_step,
                                process.output_step)
