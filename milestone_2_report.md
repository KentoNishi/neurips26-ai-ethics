# CS2760 Project Milestone 2 (Qualitative)
**Project:** Do AI Conferences’ Ethics Reviews Steer Research Practices?  
**Team:** Kento Nishi, Alec Laprevotte, Isaiah Bullock, Mfoniso M. Andrew  
**Date:** 2026-04-12

## 1) Updated project goal
We study whether conference ethics review mechanisms (ethics flags, impact statements) measurably **steer subsequent research practice** after an ethics-flagged **rejection or withdrawal**. Specifically, we ask whether later versions show substantive changes (data, evaluation, scope, release decisions) versus mainly rhetorical changes (harms/limitations framing without technical revision).

## 2) What we have collected so far
We constructed a public corpus from ICLR OpenReview records and retrieved candidate successor papers using OpenAlex (analysis pipeline + exports live in the companion repo `cs2760-ethics`).

Current corpus / retrieval totals:
- 47,893 submissions (ICLR 2021–2026)
- 185,194 public reviews
- 2,498 submissions with reviewer ethics flags (ICLR 2022–2026; ICLR 2021 lacks public ethics flags in the harvested snapshot)
- 1,857 ethics-flagged rejected/withdrawn submissions
- 6,618 candidate successor matches from OpenAlex retrieval
- 601 best-match successor candidates (not all are true successors)

## 3) Started qualitative analysis (thematic / document-based)
We began a document-based comparison workflow: for each candidate pair, we read (i) the criticized submission + its ethics-flagged reviews and (ii) the next public version candidate, then record what changed.

Milestone-2 status:
- Completed preliminary pair triage labels (LLM-assisted) to identify likely-valid successor pairs and guide sampling.
- Selected a stratified interview sample of 25 cases spanning steering categories and ethics issue types, explicitly designed for coverage rather than representativeness:
  - steering quotas: 11 ``strictly meaningful'', 6 ``intrinsic only'', 8 ``unaddressed''
  - round-robin across four issue buckets: harmful applications; fairness/discrimination; responsible research practice; privacy/security/safety
- After receiving staff approval to recruit, we sent standardized outreach emails and are now scheduling interviews as responses arrive.

Preliminary ``what changed'' snapshot (triage labels on 459 likely-valid pairs):
- 217: no observable change in successor
- 153: rhetorical-only changes (limitations/harms framing without technical revision)
- 57: methodological+procedural changes
- 14: procedural-only changes
- 5: methodological-only changes

These are preliminary triage labels used to guide sampling and manual review; they are not yet the final human-coded analysis.

## 4) Milestone-2 outputs included in this submission
- Updated manuscript draft: `sample-sigconf-authordraft.tex`
- Draft IRB protocol (class draft) and adult consent form: appended below

---

# Appendix A — IRB Protocol (Class Draft)
This draft focuses on the requested sections: 4 (purpose), 5 (procedure), 8 (recruitment), 10 (consent), 12 (data collection).

## Section 4: Study Purpose
The purpose of this study is to understand whether and how conference ethics review mechanisms influence subsequent research practice in AI/ML. We focus on cases where an ICLR submission receives ethics-related critique and is rejected or withdrawn, then examine what changed in the next public version and ask authors about why those changes did or did not occur.

## Section 5: Study Procedure
1. Identify candidate cases from public OpenReview records (ICLR submissions + reviews + ethics flags) and locate successor versions using public bibliographic databases.
2. Invite corresponding authors (or designated contacts) via email to participate in a ~30-minute video interview.
3. At the start of the call, review the consent form and obtain verbal consent to participate; separately request verbal consent to record audio (optional).
4. Conduct a semi-structured interview:
   - project timeline and revision history (submission → successor)
   - what changed (methods, evaluation, scope, release decisions, framing)
   - what drove changes (ethics review vs. other review feedback vs. constraints)
   - reflections/recommendations for ethics review processes
5. Store recordings/transcripts in access-controlled storage; de-identify transcripts for analysis; report results in aggregate.

## Section 8: Recruitment
Recruitment is conducted by email outreach to corresponding authors using publicly available contact information (e.g., institutional webpages, arXiv metadata, publicly listed author contact addresses). We received staff approval to recruit and have begun outreach.

## Section 10: Consent
We will email participants a copy of the informed consent form in advance. At the start of the call, the interviewer will:
- confirm the participant is an adult,
- summarize study purpose and procedures,
- describe risks/benefits and confidentiality protections,
- request verbal consent to participate,
- separately request verbal consent for audio recording (optional).

No signatures will be collected; verbal consent is standard for minimal-risk interviews in this context.

## Section 12: Data Collection
Data sources:
1) public documents (OpenReview submissions/reviews and successor public papers), and  
2) interview audio recordings and transcripts (if participant consents to recording).

Data handling:
- Audio recordings stored in access-controlled storage and deleted after transcription/verification (target 60–90 days, adjustable).
- Transcripts de-identified prior to analysis.
- Access limited to the research team.
- Reporting is aggregate; any quotations will be anonymized and reviewed to reduce re-identification risk.

---

# Appendix B — Adult Participant Consent Form (Draft; No Signature)
**Study title:** Do AI Conferences’ Ethics Reviews Steer Research Practices?  
**Researchers:** Kento Nishi, Alec Laprevotte, Isaiah Bullock, Mfoniso M. Andrew  
**Contact:** kentonishi@college.harvard.edu

## What is this study about?
We are studying how ethics review processes at AI conferences influence what researchers change in later versions of their work after an ethics-flagged rejection or withdrawal.

## What will I be asked to do?
If you agree, you will participate in a ~30-minute video interview. We will ask about:
- how the project evolved between the ICLR submission and later versions,
- what feedback and constraints mattered,
- whether ethics review influenced decisions, and
- suggestions for improving ethics review processes.

## Will the interview be recorded?
We will ask separately for your permission to record audio. If you do not want recording, we can proceed with interviewer notes only.

## Risks or discomforts
This is minimal risk. Possible risks include discomfort discussing peer review experiences and professional sensitivity if comments were linked to you. To reduce these risks, we will de-identify transcripts and report results in aggregate.

## Benefits
There may be no direct benefit to you. The study may help improve the efficiency and accuracy of ethics review processes.

## Confidentiality
We will store interview data in access-controlled storage, limit access to the research team, and de-identify transcripts for analysis. We will not publish personally identifying information. Because the research context involves public papers, complete anonymity cannot be guaranteed; we will take reasonable steps to minimize re-identification.

## Voluntary participation
Your participation is voluntary. You may skip any question or stop the interview at any time without penalty.

## Questions
If you have questions, contact: kentonishi@college.harvard.edu
