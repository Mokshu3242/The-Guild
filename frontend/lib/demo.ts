/**
 * One-click demo logins (14A). These passwords are public on purpose: they're in the page's code.
 * That's why there's no full admin here. "Judge" sees everything an admin sees, but the backend
 * blocks every change (members.read_only). Maya's own login is NOT listed and must stay private.
 */
export interface DemoLogin {
  name: string;
  role: string;
  blurb: string;
  email: string;
  password: string;
}

export const DEMO: DemoLogin[] = [
  {
    name: "Judge",
    role: "admin view, read-only",
    blurb: "See everything an admin sees: claims, the pool, the agent log, the money trail. Nothing you click changes anything.",
    email: "judge@guild.test",
    password: "guild-judge-2026",
  },
  {
    name: "Sara",
    role: "copywriter",
    blurb: "A member. Deliver work, ask to be paid early, file a claim when a client goes quiet.",
    email: "sara@guild.test",
    password: "sara@123",
  },
  {
    name: "Leo",
    role: "React developer",
    blurb: "A member. Gets matched to jobs and paid through PayPal Payouts.",
    email: "leo@guild.test",
    password: "leo@123",
  },
];
