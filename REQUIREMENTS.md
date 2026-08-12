# About this repo
This repo is for porting the Sega Naomi title `Senko no Ronde Special` (`senkosp`) to Sega Dreamcast.

# The rom
The rom is here: `roms` folder.

# BIOSes
Naomi and Dreamcast BIOSes are in the `bios` folder.

# References
## Cleopatra Fortune Plus
We already have successful experience of porting of a Sega Naomi title: `../cleopatra`.
I believe it (and especially its knowledge base) can be a very important source of info for this project.
Please read it thoroughly. Feel free to reuse any code from there.

## Atomiswave ports
When we were working on the `Cleopatra Fortune Plus`, our main reference were Atomiswave ports
made by fans. They can be not that important now, since we have closer example of `Cleopatra Fortune Plus`
but still it can be used for some specific cases the `Cleopatra Fortune Plus` repo cannot cover.

## The game analysis
The repo `../naomi2dreamcast` contains assessment project. Here we ranked full Naomi library.
You can find more auxiliary info, in its knowledge base and, especially, in the corresponding assessment report:
`../naomi2dreamcast/assessments/senkosp.md`

## Other sources
If you need to get more info about the platforms or tooling, feel free to clone repos or ask me to install tools
for gutting. E.g. we did this with MAME and several other tools in `Cleopatra Fortune Plus`.

# .dat
With a high chance you will need to work with `.dat` rom instead of chd or gdi. We already have toolset for this in 
the `../naomi2dreamcast` repo, feel free to use it as well as any other tools and code.

# Tooling
During working on `Cleopatra Fortune Plus` we extensively used flycast fork `../flycast4naomi2dreamcast`
for collecting data and checking hypotheses. Use it for this project.
If any updates in flycast required for this project, feel free to implement them.

You can also see that Ghidra is widely used for reverse engineering. Use it as well for this.

If the tools we use are not enough for this project, feel free to ask me to install anything else.
Or, if it is an open-source project, you can simply clone it to this repo, just like we did in `Cleopatra Fortune Plus`.

# Knowledge base
Just like in the case of `Cleopatra Fortune Plus`, I want you to document all the findings and all the solutions
to the knowledge base. It must be clear how the project was done from it for humans.
It must be easy to pass this experience to AI agents in the future for this project and for any later
porting projects.

# Necessary simplifications
If we believe to the assessment of this game from the `../naomi2dreamcast` repo, we should not face need for
compacting or cutting things. It seems like we can handle the task with memory reallocation or streaming tweaking only.
So I expect the game to behave just like it was in the arcade.

Assets cutting, compression or any other modification are considered as a measure of last resort for this project.
If it is absolutely inevitable, I need clearly understand what can be cut, 
how it will affect the game and why it is required.

# Rules
Never commit anything with copyrighted data. Just like we did in `Cleopatra Fortune Plus`.
