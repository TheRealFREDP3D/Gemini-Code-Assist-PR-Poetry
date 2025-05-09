## How I Caught My Code Review Bot Writing Poetry and the Tool I Built to Expose It 

_A story about how I built a Python tool that scans GitHub PRs for easy-to-miss AI-generated poetry and why it ended up being my most advanced and satisfying project yet._

> “This function has grown too large to maintain.
> Consider splitting it into smaller parts again.”
> — @gemini-code-assist

A few days ago, I opened a GitHub pull request on a rainy day off, coffee in hand and brain half-awake. Pretty standard stuff, until I saw a comment from @gemini-code-assist.

A bug was fixed, the tests all passed… and then, it rhymed.

> In file main.py, a bug was found,
> Now patched and polished, safe and sound.
> The tests are green, the linter is pleased,
> This PR deserves to be merged with ease!
> — @gemini-code-assist

I stared at the screen.

> “Wait… did my code review bot just write a poem?”

Could not get it out of my thoughts

![That discovery filled my head with questions.](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/ttptsil2qvw5n84hbob6.jpg)

_(Spoiler: Yes, it did — and it had been doing it all along.)_

---

## A Bot That Speaks in Verse

If you haven’t seen it yet, Gemini Code Assist(https://codeassist.google) is an AI-powered tool by Google that helps developers review code, explain diffs, and offer suggestions. It’s incredibly helpful and also, apparently, secretly a poet.

Here’s the thing: every single comment from Gemini Code Assist, reviewing a pull request, has rhythm, structure, or literary flair infused to them. Not always obvious at first glance. Once you start looking, you can’t unsee it.

Some comments are clearly poetic:

> A refactor here, a fix over there,
> This PR shows true coding care.

Others are more subtle, but still carry cadence and intention:

> This function has grown too large to maintain.
> Consider splitting it into smaller parts again.

It’s not random. It’s deliberate.
And once I realized that, I couldn’t stop thinking about it.

---

“What a weird feature… Why?”

But maybe weird is good.
Maybe it’s beautiful.

---

I prepared another pot of coffee because I knew what was going to happen. I did what I do when my "curious mode" gets triggered: follow the rabbit and end up building a tool to collect these, hidden in plain sight, poetic gems. 

---

## Introducing Gemini-Code-Assist-PR-Poetry

This project started as a simple idea: if Gemini Code Assist is adding a touch of poetry in its pull request comments, why not try to build a tool that finds and saves them?

That’s exactly what [Gemini-Code-Assist-PR-Poetry](https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry) does.

It’s a Python-based tool that scans pull requests from any public GitHub repository for comments made by the @gemini-code-assist bot, filters out the poetic content, and saves them using two formats:

- .md files: for humans who want to discover and enjoy the poems
- .json files: for machine usage (or I guess some future AI poets), available for them to analyze and remix

No generation. No modification.
Just extraction and preservation.

Even if the poems aren’t displayed in plain sight or hiding in the dark, this tool will find them.

---

## How It Works: Digital Archaeology for AI Poetry

1. **Scan Public Pull Requests**
Fetch comments from any GitHub repo/PR.  

2. **Filter for the Bard Bot**
Isolate comments by @gemini-code-assist.  

3. **LLM-Powered Poetry Detection**
Use AI to identify rhythm, rhyme, or literary devices.  

4. **Preserve the Verses**
Save poems in .md (human) and .json (machine) formats.  

---

## Using an LLM to Identify Poetic Structure

While simple pattern matching could catch obvious rhymes, LLMs detect subtle cadence and metaphor hidden in technical feedback.

Now here’s the clever part.

Because not all Gemini comments are obviously poetic, sometimes they’re hiding behind technical language, the tool uses LLM power to analyze each comment and answer one question:

Does this text contain poetic elements such as rhythm, rhyme, meter, or intentional literary devices?

This ensures we’re only collecting real verses, even if they’re hiding behind technical language or not displayed in plain sight.

The prompt looks something like this:

“_You are a poetry expert. Analyze the following text and determine whether it contains poetic structure, rhythm, or intentional literary devices. Respond only with ‘yes’ or ‘no’._”

“_[Insert comment text here]_”

If the response is ”yes”, the comment gets saved.

## Saving the Results

Once confirmed, the poem is stored in two formats:

- A human-readable .md file with formatting and grouping
- A machine-readable .json file with metadata (like date, PR number, repo name, etc.)

It’s like building a library of AI-generated code poetry, open sourced, publicly accessible, and growing with every scan.

---

## Why This Project Matters to Me

This project isn’t just about archiving AI quirks, it’s a reminder that creativity thrives in unexpected places, even in dry code reviews.

It’s about proving that creativity doesn’t always show up where you expect it. Sometimes it hides inside tools most people think are purely functional. Sometimes it speaks through a bot we assume are just trying to help us debug some code.

Building this project forced me to take some time to learn new things:

- Working with GitHub’s API at scale
- Parsing and filtering comments programmatically
- Using LLMs for classification instead of generation
- Structuring clean Python scripts that anyone can run
- Managing rate limits and authentication securely

It’s the most technically complete project I’ve ever brought to completion and the most personally satisfying so far on my coding journey.

---

## Final Thoughts

I didn’t build this because I love poetry.
I built it because curiosity struck.

In a world full of noisy bots and lifeless automation,
finding beauty in unexpected places might be the most human thing we do.

Next time you see a bot doing something unexpectedly delightful, whether it’s writing poems, drawing ASCII art, or just saying something kind, don’t just smile and be curious enough to answer the call.

Because you might end up creating your most thoughtful and satisfying project yet.

And, who knows, maybe even collect a few poems along the way.

---

## In action

The script is agile and can scan for poems in the way you want using these parameters:

```bash
$ python get_new_flowers.py --help
Starting script...
GitHub token available: True
Starting Gemini Code Assist poem collection script
usage: get_new_flowers.py [-h] [--owner OWNER] [--repo REPO] [--search]
                          [--max-repos MAX_REPOS] [--max-prs MAX_PRS]  
                          [--output OUTPUT] [--wizard]

Collect Gemini Code Assist poems from GitHub repositories

options:
  -h, --help            show this help message and exit
  --owner OWNER         GitHub repository owner
  --repo REPO           GitHub repository name
  --search              Search for public repositories with Gemini poems      
  --max-repos MAX_REPOS
                        Maximum number of repositories to search
  --max-prs MAX_PRS     Maximum number of PRs to check per repository
  --output OUTPUT       Output JSON file
  --wizard, -w          Run in wizard mode to interactively set parameters
```

---

Here is some of the terminal output when running the tool.
(Redacted and cleaned for readability)

```bash
❯ ./run.sh
Starting script...

Starting Gemini Code Assist poem collection script
Configuration: owner=TheRealFREDP3D, repo=Gemini-Code-Assist-PR-Poetry, search=False, max_repos=5, max_prs=100
GitHub token available: True

Checking specified repository: TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry
Collecting poems from TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry...
[..]
Fetching PRs from https://api.github.com/repos/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry/pulls?page=1&state=all&per_page=100
Got 3 results for page 1

Fetching PRs from https://api.github.com/repos/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry/pulls?page=2&state=all&per_page=100
Got 0 results for page 2

Found 3 PRs in TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry

Processing PR #12...
Fetching comments from https://api.github.com/repos/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry/issues/12/comments
[...]

Found 1 comments for PR #12
Comment from user: sourcery-ai[bot]
Fetching review comments from https://api.github.com/repos/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry/pulls/12/reviews
Found 3 reviews for PR #12
Found 3 review comments from bots for PR #12
Review from user: gemini-code-assist[bot]
Found review from Gemini Code Assist: gemini-code-assist[bot]

Trying to extract poem using LiteLLM with github/gpt-4.1...
[...]

LiteLLM fallback response: 

From poetry\'s hold,  
A tool for PR tales unfolds,
PullPal stands alone....

Found poem using LLM with 3 lines
Found poem in PR #12 from review
Review from user: gemini-code-assist[bot]
[...]
Found review from Gemini Code Assist: gemini-code-assist[bot]
Trying to extract poem using LiteLLM with github/gpt-4.1...

Error using github/gpt-4.1: litellm.RateLimitError: **RateLimitError**: GithubException - Rate limit of 50 per 86400s exceeded for UserByModelByDay. Please wait 29243 seconds before retrying.
Trying fallback model github/gpt-4o...

LiteLLM fallback response: NO_POEM...
No poem found by LLM
No poem found in review from gemini-code-assist[bot]
Review from user: sourcery-ai[bot]
[...]
Processing PR #2...
Fetching comments from https://api.github.com/repos/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry/issues/2/comments
Found 1 comments for PR #2
Comment from user: sourcery-ai[bot]
Fetching review comments from https://api.github.com/repos/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry/pulls/2/reviews
Found 3 reviews for PR #2
Found 3 review comments from bots for PR #2
Review from user: gemini-code-assist[bot]
Found review from Gemini Code Assist: gemini-code-assist[bot]

Trying to extract poem using LiteLLM with github/gpt-4.1...
[...]

LiteLLM fallback response: 
A bot\'s gentle verse,  
LLM\'s wisdom to immerse,
Code\'s poetry blooms....

[...]
Found poem using LLM with 3 lines
Found poem in PR #2 from review
Review from user: gemini-code-assist[bot]
Found review from Gemini Code Assist: gemini-code-assist[bot]

Trying to extract poem using LiteLLM with github/gpt-4.1...
[...]

Collected 3 poems from TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry
Script completed.
```

---

Final Output VSCode Preview

![VSCode Preview of the final output](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/waoers58m3gjpqnqg350.jpg)

---

Thanks for reading!
It's my first post on this platform. 
Feel free to comment or make suggestions.

---

If you enjoyed this story, consider giving the project a ⭐ on GitHub and sharing it with your fellow devs.

Until next time, happy coding. Have fun doing it and keep an eye out for the poetry in your diffs.

---

🔗 [GitHub Repo](https://github.com/TheRealFREDP3D/Gemini-Code-Assist-PR-Poetry)

Follow me on Twitter for more coding adventures and feel free to reach me. [@TheRealFREDP3D](https://x.com/therealfredp3d).
