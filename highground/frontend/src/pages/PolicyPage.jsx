/**
 * The terms of use and the privacy notice that registration asks people to agree to.
 * Plain language, matching what the platform actually does; the server records
 * the time of agreement (consent_at). A prototype's notice, not legal advice.
 */

import AuthLayout from '../components/auth/AuthLayout'
import { useDocumentTitle } from '../useDocumentTitle'

const PROTOTYPE =
  'HighGround is a final-year project prototype. It runs on demonstration data, and these ' +
  'pages describe how the prototype handles information; a real deployment would need its ' +
  'own reviewed notice and a named data controller.'

const POLICIES = {
  privacy: {
    title: 'Privacy notice',
    subtitle: 'What HighGround collects, why, and who can see it.',
    sections: [
      ['What we collect', [
        'Your account: name, email address, phone number and password (stored only as a one-way hash).',
        'A recovery request: the village and address, household size, flood depth, whether the home is liveable, urgency, access, and whether the household includes older people, children under five or someone with a disability or medical needs. A map pin and photographs are optional.',
        'A responder application: the organisation you act for and the supporting documents you attach.',
      ]],
      ['Why we use it', [
        'To verify requests, sort them into priority classes, spot possible duplicates and coordinate help between the district office and relief organisations.',
        'To tell you about your requests, in the app and by email. Emails never contain household details; they ask you to sign in.',
      ]],
      ['Who can see it', [
        'The disaster officers of your district see your requests, with the exact location.',
        'A relief organisation sees your contact details and exact location only while it holds a type of help on your request. Other organisations see only a summary (the village, the help needed, the household size and the priority class), never your name, address, phone number or description.',
        'Administrators manage accounts and organisations. Every significant action on a request is kept in an audit log that cannot be edited.',
      ]],
      ['Which details are required', [
        'Your name, email, phone, village and address are needed to create an account and submit a request; without them help cannot be arranged. The map pin and photographs are optional.',
      ]],
      ['Your choices', [
        'You can correct your name and phone number on your profile, and ask the district office or an administrator to correct anything else or to close your account.',
        'You can turn on two-step sign-in for extra protection; staff accounts always use it.',
      ]],
      ['How long it is kept', [
        'The prototype does not yet delete closed requests after a set period, offer a data download or have a breach-reporting procedure. These are listed as work needed before real use.',
      ]],
    ],
  },
  terms: {
    title: 'Terms of use',
    subtitle: 'The rules for using HighGround.',
    sections: [
      ['What HighGround is for', [
        'Coordinating recovery after a flood: requesting help, verifying and prioritising requests, and organising the work.',
        'It is not an emergency service. In danger, call 999 or follow NADMA and MyDIMS alerts.',
      ]],
      ['Your responsibilities', [
        'Give true and current information, and submit a request only for a household you belong to or are helping.',
        'Keep your account to yourself, and keep your password and authenticator codes private.',
        'Responders act only for their verified organisation and use household details only for the help their organisation holds.',
        'Supply appeals collect goods, never money.',
      ]],
      ['What we may do', [
        'Ask for more information about a request, reject a request that cannot be verified, or close a duplicate.',
        'Reject or revoke a responder application, or deactivate an account that is misused.',
      ]],
      ['No guarantee of help', [
        'Requests are served in priority-class order by the organisations available. HighGround cannot promise that every type of help will be taken, or when.',
      ]],
    ],
  },
}

export default function PolicyPage({ kind, onBack, backLabel }) {
  const policy = POLICIES[kind]
  useDocumentTitle(policy.title)
  return (
    <AuthLayout title={policy.title} subtitle={policy.subtitle} wide decorated={false}>
      <article className="auth-card stack policy" style={{ gap: '1.6rem' }}>
        <p className="banner banner--info policy__note"><span className="body text-sm">{PROTOTYPE}</span></p>
        {policy.sections.map(([heading, points]) => (
          <section key={heading}>
            <h2>{heading}</h2>
            <ul>
              {points.map((point) => <li key={point}>{point}</li>)}
            </ul>
          </section>
        ))}
        <button type="button" className="btn btn--secondary" onClick={onBack}>{backLabel}</button>
      </article>
    </AuthLayout>
  )
}
