# Project editor challenge

We build internal tools for a research team that keeps thousands of infrastructure project records
accurate. Those records live in an **upstream records API** that another team owns. You cannot change
it. Your job is the layer in front of it.

## Start here

1. Click **Use this template** on this repository to create your own copy in your GitHub account.
   Public or private is your choice; if private, invite `juandiegoantezana-zaga`.
2. Run the upstream API locally. Instructions, and its known habits, are in
   [`upstream/README.md`](upstream/README.md). It comes seeded with about 30 fictional projects.

## What to build (about an hour, likely less with good tooling)

Use AI the way you would on a real task here, not the way you would for a quick question. We are as
interested in how you prepared your tooling for the job as in what you asked it to do.

| Piece | What it needs to do |
|---|---|
| **A backend (Python, FastAPI)** | Sits between the browser and the upstream API. Lists projects, returns one project, saves edits to one project |
| **A frontend (React + MUI)** | A project list, and an edit form for the project's core fields and its key dates |
| **Safe concurrent editing** | Two people can edit the same project at the same time. If they change different fields, both changes must survive. If they change the same field, neither may silently win: the person saving second decides. The upstream gives you no help with this. Decide what "the same field" means for the key dates, and say why |

One hard rule: **the browser never calls the upstream API directly.** Everything goes through your
backend.

**Where this will run.** In production your backend runs as three instances behind a load balancer,
and a nightly import job writes to the upstream directly, without going through your backend. You do
not need to build either. Your design does need to survive both.

**You will extend this code live in the interview.** Leave it in the state you would want to work in.

The upstream has some awkward habits. They are in its README. Dealing with them is part of the task.
Do not modify anything in `upstream/`.

## What we are not asking for

This is deliberately more than fits in the time. What you cut, and why, is part of what we read. We do
not score UI polish, test coverage percentage, formatting, or how much you produced. Something small
that works and is honestly described beats something large that is oversold.

## What to send back

| Deliverable | Notes |
|---|---|
| **The link to your repo** | With everything committed. Replace this README with your own: what runs, what does not, and how to start it |
| **`DECISIONS.md`** (one page) | What you chose, what you cut and why, and what would break first if this had 50 editors |
| **Your AI trail** | Whatever your tooling left behind, committed or attached: how you set it up, what you told it, what it produced. Plus a short note: how you approached the task before any code was written, where the tool carried the work, where you overrode it, and what you checked by hand |

Please return it within a week of receiving this brief.

## The interview

We use the same codebase, running on your machine, with you sharing your screen. The first part is a
walkthrough of your decisions and of how you work with AI. In the second part we extend the code
together, live.

**Come with the environment you actually work in**, configured the way you like it, including anything
you have added to your AI tooling over time. Requirements will change during the session, and we want
you to respond the way you would at work, with whatever you would normally reach for. Nothing is off
limits. We want to see how you really work.

---

All projects, companies and places in this repository are fictional.
