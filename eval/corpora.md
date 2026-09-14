# Pediatric speech-disorder corpora: access plan

speechocean762 calibrates the machinery (it has enough volume and clean
annotation to fit and validate the scoring pipeline's mechanics) but it
cannot validate the clinical claim - its child speakers are healthy
developmental speakers reading isolated words, not children with diagnosed
speech sound disorders, and its L2-adult error patterns (accent/phonological
transfer) are a different population and error-generating process than
developmental articulation errors. The three corpora below are real, open
(research-use), and each fills a different part of that gap. Requests
drafted for review, not yet sent - see the bottom of this file for what
needs a supervisor's co-signature and what IRB/ethics review is likely
required.

## 1. PERCEPT-R (highest priority - get this one first)

**What it is:** Benway et al., "PERCEPT-R: An Open-Access American English
Child/Clinical Speech Corpus" (Interspeech 2022) and the companion JSLHR
paper "Reproducible Speech Research With the AI-Ready PERCEPT Corpora."
281 speakers, 203 of them children with residual speech sound disorders
(RSSD), ages 6-24. 105,232 word-level utterances, 32.47 hours, each rated
binary rhotic vs. derhotic (correct vs. misarticulated /r/) by crowdworkers
or expert SLPs. Distributed through PhonBank/TalkBank.

**Why this one first:** R is Echo's single heaviest-weighted curriculum
phoneme (57 of 390 curriculum words target it - see
`eval/phase3_within_phoneme.py`'s `echo_phoneme_weights()`), and it's the
phoneme with the clearest individual within-phoneme signal in this
project's own measurements so far (L2/all-speakers diagnostic: delta
PR-AUC +0.262, RESULTS.md). It is also the shape of task PERCEPT-R was
built for almost exactly: binary correct/misarticulated judgments on a
single target phoneme, at real clinical prevalence, on children who
actually have the disorder Echo is meant to help with. This is the
validation speechocean762 structurally cannot provide.

**Draft access request:**

> Subject: Research data request - PERCEPT-R corpus access
>
> I am an MS student at Binghamton University, working with a faculty
> supervisor on automatic detection of /r/ misarticulation in children as
> part of a speech-therapy practice application (Echo). We would like to
> request access to the PERCEPT-R corpus through PhonBank/TalkBank for
> research use.
>
> **What we are requesting:** The PERCEPT-R corpus (Benway et al.,
> Interspeech 2022 / JSLHR PERCEPT corpora paper) - word-level rhotic/
> derhotic ratings and associated audio for the 203 pediatric RSSD
> speakers.
>
> **What it will be used for:** Held-out clinical validation of an
> automatic pronunciation-scoring pipeline for /r/, trained and calibrated
> on speechocean762 (a non-clinical corpus). PERCEPT-R results will be
> reported separately from speechocean762 results, never merged into one
> number - the point is to measure real clinical performance honestly,
> not to inflate a blended metric.
>
> **What we will not do:** No redistribution of the corpus or derived
> audio outside the research team. No commercial use. No attempt at
> speaker re-identification. No publication of raw audio or
> speaker-identifying information.
>
> **Supervisor co-signature needed on:** the TalkBank data use agreement
> (PhonBank typically requires the requesting researcher's advisor/PI to
> co-sign for student requests) and confirmation of the university's IRB
> determination (see below) before audio is accessed.

## 2. UltraSuite (UXSSD + UPX)

**What it is:** Edinburgh DataShare, `ultrasuite.github.io`. Children aged
5-10 with diagnosed speech sound disorders (UXSSD) and typically-developing
children (UPX), recorded in real therapy sessions with therapist
annotations and phone alignments. Includes synchronized ultrasound tongue
imaging, which we do not need.

**Why:** small relative to PERCEPT-R, but it's real clinical audio
recorded in an actual therapy setting - a good ecological sanity check for
whether anything measured on speechocean762/PERCEPT-R (both collected
under more controlled conditions) transfers to messier, real-session audio
closer to what Echo will actually receive from a browser mic.

**Draft access plan:**

> Subject: UltraSuite (UXSSD/UPX) download request - audio only
>
> Requesting download access to the UltraSuite UXSSD and UPX audio
> subsets via Edinburgh DataShare, for the same research purpose described
> above (automatic detection of children's articulation errors,
> Binghamton University, MS research with faculty supervision). We do not
> need the synchronized ultrasound tongue-imaging data, only the audio and
> associated phone-level/therapist annotations, if a data-use agreement
> permits requesting the audio subset independently. If audio cannot be
> separated from the full release, we will request the full release and
> use only the audio and annotation files.
>
> **What we will not do:** no redistribution, no commercial use, no
> re-identification attempts. Ultrasound data, if included in the release,
> will not be processed or retained beyond what's needed to extract the
> audio/annotation files.
>
> **Supervisor co-signature needed on:** Edinburgh DataShare's end-user
> licence (typically click-through for research use, but confirm whether
> Edinburgh requires an institutional signatory for a US-based student
> researcher).

## 3. MyST (My Science Tutor)

**What it is:** LDC2021S05, Boulder Learning research agreement. ~400
hours of children's conversational speech (ages 8-11, from a
tutoring-dialogue context). Not labeled for mispronunciation - it is not
an eval/validation set.

**Why:** the acoustic model (`facebook/wav2vec2-lv-60-espeak-cv-ft`) was
trained on adult multilingual speech, not children's. If Phase 3/5 results
plateau on real clinical validation (PERCEPT-R) despite the feature
engineering working (confirmed it does, on the L2/all-speakers diagnostic -
RESULTS.md), the next lever is fine-tuning the acoustic model itself on
children's acoustics, and MyST is the volume needed for that (word
transcripts + G2P targets, not error labels - a fine-tuning corpus, not a
validation one). This is Prompt 1's Phase 7, gated on Phase 6's results,
not started yet.

**Draft access request:**

> Subject: MyST corpus research licence request
>
> Requesting a research licence for the My Science Tutor (MyST) children's
> speech corpus (LDC2021S05) from Boulder Learning / LDC, for the same
> research purpose (Binghamton University MS research, faculty-supervised,
> automatic children's speech-error detection for a therapy practice app).
> Intended use: acoustic-model fine-tuning to children's speech
> characteristics (word transcripts + grapheme-to-phoneme targets), not as
> a labeled evaluation set.
>
> **What we will not do:** no redistribution, no commercial use, no
> attempt to identify individual children from transcripts or audio, no
> use beyond the stated research purpose without a renewed agreement.
>
> **Supervisor co-signature needed on:** Boulder Learning's research
> agreement (LDC licenses for LDC2021S05 typically require an
> institutional/faculty signatory, not a student's alone) and confirmation
> of funding/cost, if the LDC membership or corpus fee applies to
> Binghamton's LDC subscription status.

## IRB / ethics review

Likely required for secondary analysis of any of the above, even though
none involve direct contact with child participants - flag these with the
supervisor and Binghamton's IRB office before sending any request:

- **Human-subjects determination.** Secondary analysis of existing,
  de-identified data collected by someone else often qualifies for
  "not human subjects research" or exempt status, but this determination
  should come from the IRB office, not be assumed. PERCEPT-R and
  UltraSuite audio, even if de-identified in metadata, are voice
  recordings of children, which some IRBs treat as inherently
  re-identifiable and therefore not fully exempt.
- **Data security plan.** Most of these agreements (TalkBank, LDC) will
  ask where the data is stored, who has access, and how it will be
  destroyed/returned at the end of the research period - have a concrete
  answer (e.g., encrypted local storage, no cloud sync, access limited to
  the named researchers) before submitting requests.
- **Minors as a vulnerable population.** Even for secondary/de-identified
  data, IRBs often apply extra scrutiny when the underlying subjects are
  children, particularly a clinical population (RSSD, in PERCEPT-R's
  case). Ask explicitly whether a full IRB application or an
  exempt-determination request is the right path - do not assume exempt
  status applies without asking.
- **Downstream use disclosure.** If any output of this research (model
  weights fine-tuned on MyST, findings from PERCEPT-R) will ship inside
  the Echo product rather than stay in an academic paper, say so
  explicitly in the IRB application and in each corpus's data-use
  agreement - "research use" and "commercial product use" are usually
  different licensing tiers, and PERCEPT-R/UltraSuite/MyST's terms above
  all explicitly exclude commercial use as currently drafted. If Echo is
  intended to ship with model improvements derived from this data, that
  needs its own, separate conversation with each data provider before
  relying on this data for anything beyond research validation.

**Ask the professor about, before sending anything:** whether Binghamton's
IRB requires an application for secondary analysis of PERCEPT-R/UltraSuite
specifically (both involve clinical/disordered-speech populations, which
may raise the bar above a typical secondary-data exemption), and whether
any of these three licenses' "research use only, no commercial use" terms
conflict with Echo's eventual product goals - if Echo is meant to ship
commercially, the professor may want to negotiate different terms (or
confirm this stays research-only) before data changes hands.
