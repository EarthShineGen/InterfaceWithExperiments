#!/usr/bin/env python3
"""Check the RECO produced from an EarthShineGen GEN-SIM.

    python3 check_reco.py reco.root

GEN-SIM is checked by check_gensim.py: GEANT took the right primaries and made
hits.  This asserts the step after that, which is the one the analysis actually
sees: the cosmic reconstruction turned those hits into tracks.

The collections below are the cosmic ones (`--scenario cosmics`), not the
collision ones.  A muon that enters from below and crosses the detector has no
beam spot, no primary vertex and no pt constraint, so `generalTracks` and the
collision muon reconstruction are not what runs and not what to look for:

  ctfWithMaterialTracksP5   tracker tracks, cosmic (P5) pattern recognition
  cosmicMuons               standalone muon-system tracks
  globalCosmicMuons         the two combined
  muons                     reco::Muon built from the above

Not every event has to be reconstructed -- a muon can clip a corner and leave
too few hits -- so the check is that the reconstruction ran and produced tracks
in some events, and it prints the per-collection rate for eyeballing.

Needs FWLite, so run it inside cmsenv.  Exits non-zero if nothing at all was
reconstructed.
"""

import sys

import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.gSystem.Load("libFWCoreFWLite")
ROOT.FWLiteEnabler.enable()
ROOT.gSystem.Load("libDataFormatsTrackReco")
ROOT.gSystem.Load("libDataFormatsMuonReco")
# Loading the library is not enough for reco::Muon: cppyy still does not know
# edm::Wrapper<std::vector<reco::Muon>> until the header has been parsed.
ROOT.gInterpreter.Declare('#include "DataFormats/MuonReco/interface/Muon.h"')

from DataFormats.FWLite import Events, Handle      # noqa: E402

TRACK_LABELS = ('ctfWithMaterialTracksP5', 'cosmicMuons', 'globalCosmicMuons')
MUON_LABEL = 'muons'


def main(root_path):
    tracks = Handle('std::vector<reco::Track>')
    muons = Handle('std::vector<reco::Muon>')

    n_events = 0
    with_tracks = dict((label, 0) for label in TRACK_LABELS)
    n_tracks = dict((label, 0) for label in TRACK_LABELS)
    with_muons = 0
    n_muons = 0

    for event in Events(root_path):
        n_events += 1
        for label in TRACK_LABELS:
            if not event.getByLabel((label,), tracks):
                continue
            size = tracks.product().size()
            n_tracks[label] += size
            with_tracks[label] += (size > 0)
        if event.getByLabel((MUON_LABEL,), muons):
            size = muons.product().size()
            n_muons += size
            with_muons += (size > 0)

    if n_events == 0:
        print('no events in the RECO file')
        return 1

    print('%d events' % n_events)
    for label in TRACK_LABELS:
        print('  %-26s %3d events with a track, %3d tracks'
              % (label, with_tracks[label], n_tracks[label]))
    print('  %-26s %3d events with a muon,  %3d muons'
          % (MUON_LABEL, with_muons, n_muons))

    total = sum(n_tracks.values()) + n_muons
    if total == 0:
        print('\nFAILURE: nothing was reconstructed in any event')
        return 1
    print('\nthe cosmic reconstruction turned the simulated muons into tracks')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
