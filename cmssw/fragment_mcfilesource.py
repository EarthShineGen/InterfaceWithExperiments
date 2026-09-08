"""CMSSW fragment for the HepMC route.

The LHE route (run3_fragment.py) goes gridpack -> ExternalLHEProducer ->
Pythia8HadronizerFilter, with Pythia switched off at every stage and used only
as a pass-through, and with the event vertex smuggled through LHE comment lines
that nothing reads without a purpose-built producer.

The HepMC route does none of that.  `ExternalLHEProducer` cannot consume HepMC,
so this is not a drop-in replacement for the gridpack: EarthShineGen is run as
its own step and the resulting .hepmc file becomes the CMSSW input source.
There is no hadronizer, because there was never anything to hadronize -- the
record is two muons and nothing else -- and the vertices come through natively,
one per muon, which was the point.

    # step 1, outside CMSSW
    ./EarthShineGen --output_format hepmc --hepmc_file events.hepmc \
        --n_events 10000 --m_X 7000 --m_A 0.23 --epsilon 1e-8

    # step 2, cmsRun with this fragment
    cmsRun step2_GEN_SIM_cfg.py

Which route to use:

  LHE     you need a gridpack, McM, and the standard central production
          machinery, and you can live with one vertex per event.
  HepMC   you want the true two-vertex topology, which with ms_model highland
          is metres, and you are driving the production yourself.

Worked and tested versions of the cfgs below live next to this file:

    gensim_cfg.py          GEN-SIM from a .hepmc file
    check_gensim.py        what GEANT made of it
    run_gensim.sh          the two steps plus the check
    read_hepmc_cfg.py      the format-level read-back
    check_hepmc_roundtrip.py
"""

import FWCore.ParameterSet.Config as cms

# ---------------------------------------------------------------------------
# THE SOURCE
# ---------------------------------------------------------------------------
# MCFileSource reads HepMC 2 (HepMC::IO_GenEvent ASCII) and produces an
# edm::HepMCProduct under ('source', 'generator').  It is the only file-based
# generator input source in CMSSW; there is no HepMC3 file reader, which is why
# EarthShineGen writes HepMC 2.

source = cms.Source(
    "MCFileSource",
    fileNames=cms.untracked.vstring('file:events.hepmc'),
    # MCFileSource has no fillDescriptions, so this ProducerSourceBase
    # parameter has to be given by hand; it has no default.
    firstLuminosityBlockForEachRun=cms.untracked.VLuminosityBlockID(),
)

# There is no ProductionFilterSequence: no generator module runs, because the
# events are already generated.  A cfg built with cmsDriver should be given
# `-s SIM` (not `GEN,SIM`) and have its source replaced by the one above.

# ---------------------------------------------------------------------------
# THE VERTEX
# ---------------------------------------------------------------------------
# Read this before running through GEN-SIM.
#
# EarthShineGen's 'detector' stage puts each muon on the hand-off surface
# around the detector, travelling inward and upward.  That position is per muon
# and it is the whole point of the signal, so the standard beamspot smearing is
# wrong here: it would move both muons to the interaction point.
#
# So: no VtxSmeared step at all, and g4SimHits reads the source product
# directly.

GENERATOR_PRODUCT = cms.InputTag('source', 'generator')


def customise_for_earthshinegen(process):
    """Point GEANT at the unsmeared record and let it see off-axis primaries.

    Call this on a cmsDriver-produced SIM cfg after replacing its source.
    """
    process.g4SimHits.HepMCProductLabel = GENERATOR_PRODUCT
    process.g4SimHits.Generator.HepMCProductLabel = GENERATOR_PRODUCT

    # ApplyPCuts stays ON deliberately.  SimG4Core's Generator computes
    #     fFiductialCuts = fPCuts || fPtransCut || fEtaCuts || fPhiCuts
    # and starts every particle from `toBeAdded = !fFiductialCuts`, so turning
    # every cut off makes GEANT track the whole record -- mock beams and dark
    # photon included -- instead of just the status-1 muons.  One cut has to
    # stay on; the window is opened instead.
    process.g4SimHits.Generator.ApplyPCuts = cms.bool(True)
    process.g4SimHits.Generator.MinPCut = cms.double(0.04)
    process.g4SimHits.Generator.MaxPCut = cms.double(1.0e6)
    process.g4SimHits.Generator.ApplyEtaCuts = cms.bool(False)
    process.g4SimHits.Generator.ApplyPhiCuts = cms.bool(False)
    process.g4SimHits.Generator.ApplyPtransCut = cms.bool(False)

    # The Run3 era switches on the PPS beamline transport, whose producer only
    # exists in the SimExtended sequence.  No forward protons here.
    process.g4SimHits.LHCTransport = cms.bool(False)

    return process

# ---------------------------------------------------------------------------
# WHAT GEANT ACTUALLY TRACKS
# ---------------------------------------------------------------------------
# The record is built so that this comes out right without further help.  The
# A' and the muons as produced carry status 3 -- decayed by the generator, do
# not propagate -- and only the two arriving muons are status 1.  That matters:
# SimG4Core hands GEANT every status-2 particle whose end vertex is outside the
# beampipe, so status 2 on the muons as produced would have GEANT start
# tracking them at the decay point, a kilometre underground.
#
# Choosing the sample: `require_hit detector` (the EarthShineGen default) only
# asks that the muon reach the hand-off surface, which is the detector's own
# outer cylinder and therefore satisfied by construction -- most such muons
# clip the outside and never enter CMS.  For a GEN-SIM sample ask for
#
#     --require_hit inner_detector --require_both_muons 1
#     --detector_half_length 11
#
# (11 m rather than the generic 15 m because beyond that there is no CMS left
# to hit).  With those settings every event leaves hits in the muon system and
# nine in ten in the tracker.
