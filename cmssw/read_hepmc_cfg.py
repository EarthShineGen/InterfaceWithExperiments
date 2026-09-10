"""Read an EarthShineGen HepMC file back with CMSSW.

    cmsRun read_hepmc_cfg.py inputFiles=file:events.hepmc [maxEvents=-1]
    cmsRun read_hepmc_cfg.py inputFiles=file:events.hepmc3 hepmcVersion=3

`MCFileSource` (IOMC/Input) opens the file with `HepMC::IO_GenEvent` and reads
HepMC 2.  `MCFileSource3` (cms-sw/cmssw#51842, same package) reads the
generator's native HepMC 3 and produces `HepMC3Product` +
`GenEventInfoProduct3`.  Both put their product at ('source', 'generator') and
`GenParticleProducer` consumes either, so nothing below this line changes with
the version.

Nothing here needs to be compiled -- every module is a release plugin.

Three things are checked:

  * the file parses at all, and every event comes back;
  * `GenParticleProducer` turns it into reco::GenParticles, i.e. the PDG IDs,
    statuses and mother/daughter links are well formed;
  * `ParticleListDrawer` prints the table for eyeballing.

The vertices -- the actual reason for using HepMC -- are checked numerically by
check_hepmc_roundtrip.py, which reads the ROOT file this cfg writes.
"""

import FWCore.ParameterSet.Config as cms
from FWCore.ParameterSet.VarParsing import VarParsing

options = VarParsing('analysis')
options.setDefault('inputFiles', ['file:events.hepmc'])
options.setDefault('outputFile', 'hepmc_read.root')
options.setDefault('maxEvents', -1)
options.register('hepmcVersion', 2,
                 VarParsing.multiplicity.singleton, VarParsing.varType.int,
                 'HepMC version of the input file: 2 is read by MCFileSource, '
                 '3 by MCFileSource3 (cms-sw/cmssw#51842).')
options.parseArguments()

process = cms.Process("READHEPMC")

if options.hepmcVersion == 3:
    process.source = cms.Source(
        "MCFileSource3",
        fileNames=cms.untracked.vstring(options.inputFiles),
    )
else:
    process.source = cms.Source(
        "MCFileSource",
        fileNames=cms.untracked.vstring(options.inputFiles),
        # MCFileSource has no fillDescriptions, so the ProducerSourceBase
        # parameters have to be given by hand; this one has no default.
        # MCFileSource3 does have them.
        firstLuminosityBlockForEachRun=cms.untracked.VLuminosityBlockID(),
    )
process.maxEvents = cms.untracked.PSet(
    input=cms.untracked.int32(options.maxEvents))

process.load("FWCore.MessageService.MessageLogger_cfi")
process.MessageLogger.cerr.threshold = 'INFO'
process.MessageLogger.cerr.FwkReport.reportEvery = 10

# The particle data table GenParticleProducer needs.  The A' is written with
# the hidden-valley PDG ID 4900022, which the table does not know; that is why
# abortOnUnknownPDGCode stays off (it is off by default anyway).
process.load("SimGeneral.HepPDTESSource.pythiapdt_cfi")

process.genParticles = cms.EDProducer(
    "GenParticleProducer",
    src=cms.InputTag("source", "generator"),
    saveBarCodes=cms.untracked.bool(True),
    abortOnUnknownPDGCode=cms.untracked.bool(False),
)

process.printList = cms.EDAnalyzer(
    "ParticleListDrawer",
    src=cms.InputTag("genParticles"),
    maxEventsToPrint=cms.untracked.int32(3),
)

process.out = cms.OutputModule(
    "PoolOutputModule",
    fileName=cms.untracked.string(options.outputFile),
    outputCommands=cms.untracked.vstring(
        'drop *',
        'keep *_source_*_*',
        'keep *_genParticles_*_*',
    ),
)

process.p = cms.Path(process.genParticles * process.printList)
process.e = cms.EndPath(process.out)
