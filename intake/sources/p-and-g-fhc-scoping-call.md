# Gong call transcript: Atlan PoC Context Studio Use Case - F&HC-20260430 110253-Meeting Recording

**Source:** https://us-23254.app.gong.io/call?id=8832468837587284987
**Call date:** 2026-04-30
**Duration:** ~109 minutes
**Segments:** 395

**Context:** Atlan PoC Context Studio Use Case scoping call with P&G's Fabric & Home Care (F&HC) team. This is the customer scoping conversation used as the input artifact for the agent-building exercise.

**Participants identified from introductions:**
- Emily lash (P&G) — Fabric and Home Care partner success leader, DNA team
- Diana (P&G) — product owner, decision engine
- Kim Bushfield (P&G) — DevOps for fabric care commercial
- Emily Vu (P&G) — embedded data scientist in fabric care
- Megan (P&G) — DNA platforms team, data discovery & AI-ready data
- Himanshu Sikaria (Atlan) — data scientist by background
- (Plus other Atlan team members)

**Note:** Glean returned the transcript without speaker labels. Each segment is rendered as a paragraph. The `\u0004` separators within Gong's raw text have been converted to spaces. Timestamps are HH:MM:SS from call start.

---

[00:00:00] that's two.  Yep.  Go ahead.  Okay?

[00:00:01] Perfect.  Thanks all for joining.

[00:00:05] The.

[00:00:05] intention today is, you know, we'll go through the use case that's been shared, do a quick round of introductions, align on the use case, we'll replay back what we've understood from the use case and then hopefully seek validation as per your understanding as well of that.  And then the end goal today is to really align ourselves for Cincinnati in two, three weeks time, right?  So we can actually hit the ground running there and make sure we're actually building and actually with the intention of putting this into production.  So get all the legwork out of the way here, all the tooling, architecture, conversations, understanding of the use cases, mutual goals, et cetera.

[00:00:42] Let's get all of that out of the way today.  And then we can really sort of build and bring this to life in a couple of weeks.  So, but let's start with some introductions.  Always nice to see yous in the room.  So, if we start with PG, so I'll do a roll call as I see people on my screen.  And then we can just do a very quick 10 15 second introduction Emily?

[00:01:01] Which one?

[00:01:02] Emily lash?

[00:01:04] Okay.  Hi, I'm Emily, my role at PG is the fabric and home care partner success leader.  So basically what that looks like is just me making sure that fabric and home care understands all the capabilities that we provide centrally as part of DNA.  So nice to meet you guys.

[00:01:26] Perfect.  Diana.

[00:01:28] I am coming on as the product owner.  Yeah, we know you're wrong.  Yeah, gonna be working with me on decision engine.  So, yeah.

[00:01:40] Which is one of our big AI priorities is what we're calling it within DNA.

[00:01:47] Perfect.  Kimberly.  Hi.

[00:01:50] Kim bushfield.  Sorry about the camera, but I'm homesick today.  So I'm just going to remain off.  I am devops for a fabric care commercial.

[00:02:01] Wishing you speed of recovery, Emily?  Vu.  No.

[00:02:07] You can just talk.  Hi, I'm Emily, I am the embedded data scientist in fabric care.

[00:02:14] Perfect.  And last, but not least, Megan.

[00:02:17] Yep.  Hi, everyone.  So, Megan, I work within DNA platform's team specifically on data discovery and AI ready data.

[00:02:26] And we'll just go round atlan.  Himanchu.

[00:02:31] Awesome.  Good to see everyone.  I started my career as a data scientist.  So, I relate to a lot of you in the room here and to a lot of data problems.  And now AI problems all of us are facing at atlan.  I lead our entire customer experience group here, working very closely with customers and helping them cross the chasm on this chaotic but exciting AI world.

[00:02:57] Perfect.  And Mathura, sure.

[00:02:59] I can go next.  Hey, folks.  I'm Mathura, been at atlan pretty much since day one today.  I help lead our new products, go to market along with himanchu, and a few others.  We, you know, the needs of the enterprise have been changing rapidly with AI.  And so we've been working very closely with our customers on getting them to go to value and success with their AI program.  So, very excited to dig in deep and see what you've all built together.  Okay?  Deb?

[00:03:32] Hi, my name is deb.  And I.

[00:03:35] am a.

[00:03:36] staff PM in the new product org and building out the context engineering studio.  I've got a background in machine learning, deep learning and trying to make these applications a reality for a little while and really excited to see where the world is moving with agents.

[00:03:54] Perfect.  And Tim, hey, I'm Tim.

[00:03:58] I've been with atlan for a little less than a year.  Now, I'm a csa here and my background is very much heavy in data engineering.  And now I'm starting to shift over to the AI world and doing a lot of work there.  And I'm excited to hear about your use cases and your stack.

[00:04:15] And Andrew, yeah.

[00:04:18] Andrew, definitely not a day scientist.  I can safely say by background, but yeah, I've been with atlan for a couple of years and I've been working with Megan and the data discovery team since before go live with atlan.  So, yeah, looking forward to hearing more about this use case and we've got Gary as well.  Don't forget.  Yeah, Gary.  Hi, everyone, Gary, I work in product as well.  And with deb and Megan, we met at Gartner had a conversation.  So, looking forward to the continuing discussion here.  Nice to meet you all.  Perfect.

[00:04:48] And I'm atlan account director here at atlan and work very closely with Megan and team.

[00:04:52] In fact, at all hours… we're team zinger, I don't know all times of the day.  So, yeah, look forward to engaging on this with you guys.  So, but firstly, thanks very much for sharing the use case.  You know, you guys are super organized and with some great reading that we had to do behind the scenes.  So what we're going to do is like I mentioned right at the beginning, replay what we've understood from your use case and your requirements.  And Himanshu will drive that we'll do some white boarding and then we'll hand the baton over to you guys to see whether, you know, as like I said, if we've understood that correctly, whether sort of there's any gaps and then take it forward from there in terms of how we build from now towards Cincinnati.  So with that Himanshu over to you.

[00:05:36] Thanks, Milan.  Before I share, we were just trying to whiteboard and deconstruct the entire report you had firstly.  It was very well built out and very well detailed.  We rarely get those from our customers.  So really appreciate you spending that time and sharing that across quick question.  Before we go deeper.  Can you like just help me with like is this like one of the projects inside your entire decision engine which you were talking about?  Or like where does this stand?  And the current state of the project that'll just help us?  And from there we can go deeper into this?

[00:06:12] Take that, Emily, I can.

[00:06:15] So, yes, this is one of these cases.  There are many that will come out.  But basically, it's the first use case that we're starting with this and we are focusing on two of our business units.  We have like 10 or 12 now.  So we're focusing on the two biggest ones to start with.  And I don't know Megan if you like.

[00:06:43] What?

[00:06:44] You shared in terms of the pre read?  So yeah, I just shared the.

[00:06:48] Document you sent to me on the work, you guys have already tried the fabric here?  Yeah, perfect.  All right.  Yeah.  But yeah, no, I think so decision.  It's rather a newer thing that we've I think in January, our central lead team aligned that these were their top priorities from an AI use case decision engine, became the one that DNA would focus on.  From there, we're partnering with fabric and home care as our lead use case.  Ou, I should say and within the, ou, there's multiple use cases as well.  So, yeah, a couple of different paths that different teams are taking.  We want to understand and learn a little bit more about what atlan can do and to understand if this is a direction we should be taking or how we should be thinking about it.

[00:07:31] Is that fair?  Yeah, awesome.  This is helpful.  Let me share my screen and we'll go generally, team's meeting is not kind with me.  So let's see if this works.

[00:07:53] You'll see my whiteboard.  Yeah, I don't know if you can zoom in a little bit Himanshu, but we can see it.

[00:07:59] Yeah, it's kind of a weird… yeah, sort of cutting it though.

[00:08:06] Oh, weird.  OK.  Let me share my entire window.

[00:08:15] Is this better?  Yeah, much better.  OK, perfect.  I know we have two hours blocked.  So I hope we'll figure out how much time we need for the entire session and we'll go from there.  But overall, from what we understand so far, so one is the goal right now is for fabric care.  And again, you have detailed out the entire four steps in the process.  But the goal here is to analyze brands better and see if something's increasing or decreasing, what's the reason?  And the goal is the why to find behind it because why is the harder analysis generally?  What is an easier analysis?  Is that understanding, right?

[00:09:07] OK, perfect.

[00:09:09] So, based on this for today?

[00:09:13] We thought.

[00:09:14] We could just walk through on what we understood and go slightly detailed on the steps which you mentioned.  And from there, we can see if there's a future architecture which can align better, knowing what the current pain points and where you are in the project right now.  OK, feel free to just talk to me if at any point, you think I am… not making sense or I am misunderstanding and representing what you had.  So, just like pause me at that, any time there.  So, what we understand is if it's if a question like this is like for gains team analyst, if you're seeing that target is dropping in sales, we want to know the why.  So right now, the core sources which you're feeding into this, is your all outlets share, create panel, decom, all of the other tables you might have.  The first step is to do the brand analysis.  So, going deeper into parsing the question from the user, understanding the filters, building the SQL queries, analyzing the SQL queries, and then creating an end output for the phase two to use.  Is that, is that highly correct?  Yes.

[00:10:37] That's the first step.  Do you want to add anything to that?

[00:10:49] No. OK.  Yeah, that's right.  Got it.  And in here, we understand you would be like, and all of this is langrath, right?  All of these steps are being executed inside of langrath.  Yes.  Got it.  And in that case, like, how are you actually feeding?  I'm, sure.  Like, in the document, also, you mentioned that like there's aos, metric definitions, there is the there's like I'm sure.  There'll be like some table details, some like SQL templates, like how are you feeding all of this today, into langrath, and where is this coming in from?

[00:11:30] So the aos?

[00:11:30] Table details are, in a Json file, same with aos metric definitions, and.

[00:11:38] I, can you go back to the slide?  Sorry?

[00:11:43] I'm just trying to make sure I'm able to see everyone but, give me a second.  I'm navigating through this.

[00:11:50] There you go.

[00:11:53] The.

[00:11:54] SQL templates, that's in like a constants file, and that needs to be specified for each table, and.

[00:12:05] then see how?

[00:12:07] To analyze those are set, given as a set of instructions to an LLM got it.

[00:12:14] Got it.  It, would, it would be fair to say, and you guys correct me if I'm wrong, but it would be fair to say, you know, if atlan had a different way to serve up the context, I don't think we're against understanding how that would look.  Is, is that an okay assumption?  Yeah.

[00:12:29] Yeah.  I think that's fair.  I think the things that we already know we can move into atlan are like these definitions for the different table structures and columns, and everything like that, right?

[00:12:43] But the,

[00:12:43] additional context, if there is a way, to have that held there as well, is something we're interested in?

[00:12:52] Got it.  And, for some of these, other pieces like product granularities market definitions, are these also just going inside the instructions today or is it stored somewhere centrally?

[00:13:04] They're each stored in their own Json file.  And then for each step, if they're necessary, they're provided to the LLM?

[00:13:11] But it's not central.  Right now.  It's like local, in the code.  So, and a lot of that to be Frank, a lot of the, all three of those really, the SQL writing as well are definitely reusable across like multiple different use cases, different ous, I would expect that there might be some need to, like customize a couple of them like on top of the core base, but, that's something we're interested in understanding as well as like if there's a way to have like a central product granularities definition and then have like a okay for fabric care specifically, there's this additional business like context on products that you need to know or for this specific brand, we like to look at things like in a certain order where another brand, we might go through product attributes in a different order.  For example.

[00:14:08] Got it.  So,

[00:14:10] Sorry.

[00:14:11] One follow up there, you said like this is currently stored in a Json.  Curious, how did you actually build that Json?  Like did you have like, some internal documentation?  Did you manually fill it up?  Like, how did you build that Json chat?

[00:14:24] PG… we use an LLM to help us create it based on like our context that we have.  So, we just like kind of put all the context in and said, help us build a Json to do this?  Got.

[00:14:40] It?  And was that like context stored in like your internal wikis or like, was it just like slack it?

[00:14:46] Was in?

[00:14:46] Kim's,

[00:14:49] brain, we,

[00:14:50] do have a product hierarchy if you will of like the explanation.  And then we take that with the combinations that are available that fabricare cares about.  And then that's what was created with the Json.  So there is tables behind it that you can re, utilize to create that granularity… got.

[00:15:13] It.  Okay.  And what I'm.

[00:15:16] hearing is given this was like a one time agent.  A lot of this is like locally defined as we scale across bus and across use cases within the same BU as well.  We'd want to figure out ways of centralizing this.  I think even.

[00:15:30] To be able to run this specific workflow in a productionized environment, like we would need to figure out how to keep this context somewhere that it can be like referenced again and again versus being stored, you know, in some in just in the workflow itself.  Got it.  And,

[00:15:51] as a, from a central perspective is like landgraf, the chosen agent framework.  I know you also mentioned like anthropic somewhere in our past discussion.  So just wanted to check if landgraf is the chosen thing or are you exploring something else.  I think we're always.

[00:16:08] open to other options.  But right now, landgraf is like the main way that we build out agents.  Okay?  Makes sense.  It's the preferred way it's the preferred way.  Yeah, exactly.  And we are looking into like anthropic skills as well.  But I imagine this would still be referenced by landgraf.  Yeah.

[00:16:31] Yes, I think landgraf's supporting skills, which is we'll hopefully get to that shortly.  Okay.  Just moving on here.  The end of this, I'm assuming is we run all of these queries.  I know that you have the four cross two, like all the SQL templates, which is across your different timeframes across different categories.  So that the agent has all the different context and it's not boiling to a specific SQL query.  So that's almost like hard coded in there.  And this phase two is basically going to the more on the why and the conditions.  So this is more on trade penalty.  Com more in that realm.

[00:17:17] Yes, correct.  And like later on there may be a myriad of different tables that we would want to be able to navigate to and like run analysis on based on the question.  So right now we have it limited to just like trade panel or decon.  But there may be many different tables that we would want to navigate to get more information dependent on the question and what we're trying to diagnose.

[00:17:46] And all of these are also in like databricks or bigquery for you?

[00:17:50] Yes, theoretically.  And.

[00:17:53] practically, is it like Google sheets and like excel files?

[00:17:56] No, no, no, they are either in bigquery or databricks.  Yes.  Oh, yeah.  I'm trying to think if there's anything that's outside of that, I don't know, Kim, Emily, I don't know, not that we would try.

[00:18:13] To scale, no, no, we don't want to do that outside of databricks or bigquery.  The only thing that I want to say on phase two… this, Emily Vu, you and I talk a lot about the three paths in this and it's not really represented necessarily in here of knowing that the market analysis is done on like the different product granularities of knowing, that yyy can have the different paths to it.  So I'm making sure that you kind of take a note on that particular path aspect of it.  So it's not just a linear way.

[00:18:58] To.

[00:18:59] go about it.  There's other information that can be like have like two more lines of phase one and phase two of different ways that you can look at it.  So like phase one, you would have a granularity of category manufacturer like three different granularities to do that market share analysis off, which.

[00:19:21] is just a different way.

[00:19:22] of looking at it.  But again, it's creating information… that would be used later on that deep dive.  So you have one that goes down a path that says what does the question, what's the question context?  And then another one that's based off on that high level market share analysis.  And then the third is to have that above and below the line of the question to go into phase two to give that, why?  Why?  So, it's not necessarily this linear kind of unless your scope of this is just to do the top line executive report.

[00:20:13] I think that's kind of summarizing the 16 aos queries because right now it's like it's all being generated and then all the analysis being done.  And that's because it's like a really prescriptive path, but we would like to get to a more of an agentic flow where we can get the insights from each of you.  And I guess as Kim was saying, it's not linear, be able to navigate through the analysis without having to hard code all of that.  So that's.

[00:20:48] in step one B, basically where you see create SQL queries that result in views of the data that will be used in the downstream analysis.  So basically what we're doing is based on the context of the question asked, we go and look at different levels of.

[00:21:04] The.

[00:21:05] hierarchy from a product standpoint, from a market standpoint.  To try to understand, let me just give you an example.  The question that we kind of focus on in this example is at target.  Well, in order to know how things are going for gain at target, you also need to understand like how is overall fabric care?

[00:21:24] You know.

[00:21:25] Working like doing in the market, how is target doing in the context of other retailers?  How is gain doing in the context of PG, in the context of competitors?  Et cetera.  So you run all of these queries, and then you use that as input to kind of define what your next steps are.

[00:21:43] Does that make sense?  All right?

[00:21:45] So based basically in one P, in here, when you're building these grids, almost, which is like at four different levels, two different markets, two different time modes, this.

[00:21:59] Right now?

[00:22:01] It is like defined as these 16 views, ideally in a more agentic way that this would like the agents would be able to navigate through this, change this more dynamically and not just have a hardcore linear path.  Did I understand that, right?

[00:22:18] It's based off the question, it's based off.

[00:22:20] The question, so like what do you have here that query you aos, the question that is coming in that Emily was describing was around target being the market target as the retailer target.  That would give us because we have like over 400 markets.  It is selecting two of those.  Or there's actually five markets that have target name in them just for simplistic sake.  So those five target markets can be brought in.  But those five target markets have different descriptions of what they're utilized for one is like a total target.  One is like dcom one is in stores.  So just to give a generic thing, so we would want to analyze what is the best from that context of the question of what they're asking for.  So if they said anything about online, you would go and select like the dcom or if it's selected, otherwise, it's like maybe we just default it to total target.  And then the other two market described is the context of the question is around target.  And as Emily was describing like the context around how am I doing in the market?  It's usually utilizing a different market name called total usaos.  So I would know how I'm doing in the total market versus just how I'm doing in the total market of target.  And the four levels of granularity is like… if I'm doing it at a category level or category manufacturer level, or category manufacturer, brand level, depending on if the question that was asked was down to the brand level or if the context of the of.

[00:24:20] What we.

[00:24:20] absolutely want to make sure we measure against is about category and category manufacturer.

[00:24:29] All right.  Okay.  This is helpful.  Thank you for doing a one on one on this.  Some of this, I'll just repeat what I understood here is one given, the first thing is to choose the market because you'll have the entire standardized market definitions.  So based on the question, we'll have to figure out the market which I'm assuming like based on one, a, you are able to pass to the filters to figure out if it's a category manufacturer, like figure out all the different filters there.  And then based on that figure out what that grid should look like.  And based on the market share analysis, then in two, a you'll pick up the right data for the yyy which is either a dcom for digital or trade panel.

[00:25:18] Did I capture that?

[00:25:24] Yes, I think so.  But it's.

[00:25:26] not just the product level.  So I just want to make sure that that's clear in terms of like what needs to be detected.  It's the product level.  It's the market like granularities as well.  And the time period we also would want to.

[00:25:41] Be able to navigate across like within and across.  So, for example, like we.

[00:25:46] could start with the question, could.

[00:25:47] be asking about brand, but you.

[00:25:51] might.

[00:25:52] want to look at the brand across?

[00:25:53] The different markets or look at how each manufacturer is performing or like the different sub brands or forms and sets of that?

[00:26:06] Brand.  So,

[00:26:07] that's something that right now we can't do that with our current I guess descriptions just currently.

[00:26:15] With what we have because it's not generalized enough or what's the it's not generalized enough.  In the context we don't have the.

[00:26:24] Definition either.  Though actually Emily, it's like if I'm asking about gain and the context that is missing is knowing that gain would also like to know about their price rotations and going down to that level of granularity to do some yyys because that's how the business is being done just for clarity on the selecting the business view.  The business view being understanding is not necessarily a trade panel.  It's called BBB.  I'd rather stick to that because trade panel means a data source and it's not just that data source that describes what business… view that I'm looking at.  Dcom says, I'm looking at dcom markets and dcom business… and tradepanel isn't really a business.  It's called the vbb model.

[00:27:24] Is it like BBB?

[00:27:26] Sorry, my voice is horrible.

[00:27:33] Vbb.

[00:27:35] Thank you.  Oh, so tradepanel.  So vbb, there's another B. So Victor, bravo.

[00:27:48] Yeah.

[00:27:49] Is the thing tradepanel is a data source under vbb, and so is hhp, so, is other data sources underneath it?  So it's really the business view and there can be additional ones that are added.

[00:28:08] All right.  Okay.  Which makes sense.  And because right now, I'm just trying to understand the reason is like one, if you're looking at like gain, you want to go like one understand how gain generally does its analysis because gain will have a specific way of doing it.  And then you want to also look at like more parallel above or beyond gain when you're doing gain analysis as well, which is restricted because right now, it is a more deterministic step.

[00:28:39] It's more of like… understanding… how each one of them does.  So vbb is how we analyze the business in a generic sense.  We also break up the business underneath that and saying like, okay, let's look at the dcom business and that's just a different business context that I would describe.  And then if I were to say I want to look at gain specifically, I could say that's a lower level business context because it is underneath vbb and I would get to that explanation of what that model, that business model looks like.  But it would have additional lower level information that is necessary to do that analysis across.

[00:29:32] I think there are two pieces.

[00:29:35] Of.

[00:29:35] context that need to be represented, right?  So, one of them is how you look at the business based on what business you're talking about, because like the brands have different ways of analyzing their businesses, meaning they have different attributes that they look at, although they may look at the same metrics across now, then the vbb versus the dcom.  Like these are different kind of modalities, they have different metrics and different data that support diagnosing them.  So that's why you have like these two additional pieces of context.  One is, how do I look at the business depending on what business I am asking a question about, right?  And I have to know that business context to say, for example, for gain, we don't have an attribute of sub brand.  So I would never look at the sub brand under gain to see what's happening like below the brand level.  Whereas with tide, I would, right?  So that's a piece of context that I don't think we have represented right now in our model at all.  And then the second one that we're kind of like hard coding at this point is if it's dcom, go look at this dcom metric.  If it's not dcom, look at vbb that's where you have to understand like what data is going to best serve?  The diagnostic part of the question that I'm asking and then be able to navigate to the right table based on that.

[00:31:09] Input.

[00:31:12] Got it.

[00:31:13] And today, some of this is hard coded in your instructions.  Yes.  OK, perfect.  I think in that case, so, and so the yyy analysis is basically picking up the right view again writing SQL and doing a diagnosis on top of that.  So it's the same like a similar step but on a very different set of tables.

[00:31:42] Yeah.  And here, I think one of the things that we need to think about as well on top of like navigating to the right table to get the right diagnosis based on the question is also how the different measures in each of the different data structures, like relate to each other in order to diagnose the business?  Because I think that part is also we've been looking into potentially building out knowledge graphs for this, but we're wondering like if there's another way to manage it from a contextual point of view.  And I know in atlan, you also have like where you can have different measures having lineage to each other.  So like not just the data structure lineage but the measure lineage, that could be really helpful context for the agent to be able to help like know how to diagnose the different metrics.  So as an,

[00:32:39] example, if you're looking at like percentage acv, so if it knows like what are the other metrics this is linked back to the agent will have a way to navigate through it rather than just getting stuck to acv.

[00:32:52] exactly.  Or.

[00:32:53] Like a lot of times it happens like distribution points like it's always like distribution points went up or distribution points went down and it's like that's only so helpful like it doesn't really tell, you know, what actually is happening and why did distribution change?  So.  Yeah.

[00:33:11] Got it.  And today, are these measures mostly in Power BI for you or is this coded in the tables and the data?

[00:33:21] It's a bit.

[00:33:22] Of a mix.

[00:33:24] Go ahead.  Kim, they're coded in both to be blunt.  It depends on when they can be, and they can also be derived.  The model itself.  Most… of it is inside of databricks… roll up and roll down at when we have that capability inside of Power BI, we'll go and have that different level of table generated for that.  So we have a combination.  And so I would say both, got it.  We have another.

[00:34:10] Use case too within home care that we didn't share up front.  And I won't go into the details of it now, but basically, they are using Power BI exclusively when they have their rlm interacting like their agent interacting with the data.  They're using only Power BI as the basis.  But yeah, till.

[00:34:31] The time it's somewhere encoded, be it in Power BI or in data, I think we should be good.  Just wanted to make sure that it is somewhere in the data… world and not lying somewhere out of that, which is always better especially for the relationships Emily, which you spoke about because we'll be able to backtrack and create a metric map is what we call.

[00:34:54] Okay.  Perfect.

[00:34:55] And then I think phase three is mostly just using all of this and this is where probably you'd be using most of the agentic work to generate the HTML today.

[00:35:05] And how.

[00:35:07] do you serve it to your end users?  Is that something you've thought about?  I know you've mentioned about chat, there's requests you get what's the ideal way for users to actually consume this.  Have you gotten to that state not?

[00:35:24] Yet, but Kim, I think you can share what your vision is.

[00:35:30] Ideally, it would be everything… but think of it this way we have reporting in Power BI, right?  So that's one thing we also have reporting inside of looker, we have… actual analysis that wants to be real time, which would have to have a web front end.  So there's that.  And then there's also if you think about it, if… you have the direct connection between… oryx, and atlan, you can do analysis on the back end too of what the questions and everything else are.  So like that repository and having that capability over that aspect of it, the other inputs of it more than just asking questions from a front end like having like Samantha, which is our like alerting capability.  So an automatic feed into it for problem areas that were like analyzed or monitored would be coming in as a question that would be like automated question, put it that way that we could manipulate to ask the correct kind of question.  But it would be automated.  So a lot basically.  But, and Emily is smiling because I always ask for a lot but we can figure out what can and cannot be done.  Yeah, it needs to.

[00:37:09] Be multimodal at the very least, like there needs to be the ability to kind of like chat with your data and go back and forth until you get the answer you're looking for and then potentially build a report off of like the findings.  But I think there also needs to be functionality for people just having a simple question like imagine an executive leader is about to go into a meeting with a business and they just want to see like where do things stand?  So I would imagine that type of capability as well.  And.

[00:37:40] So, some that are not even based off of like think of it as a new person coming in and needing to do analysis on the data.  And there's like, well, where do I find X y Z?  They can ask that kind of question that you want to go find where your data is as well.  That is also kind of a use case of. it.  Got it.

[00:38:04] And with that one, we already actually used the MCP server with atlan to do like a find my data with Microsoft.  So at least we know it can find reports and it worked really well.  That was definitely, I'm sure we can.  I'm just saying that one has already been like proven.

[00:38:26] Okay.  Which is always great.  Seeing it in action.  And we'd love to go deeper there MD at some point.  But sticking to this before this agentic world, was this encoded in a python for you?  I know MD, you have been working on some of this as well.  So what was happening before the agentic world here?

[00:38:47] Right now, this is just like people navigating through Power BI, reports, right?  And, or having access to the raw data and then using their own tools, maybe python, maybe excel, maybe… building their own Power BI's and creating metrics off of that.  And then a lot of training is given to the analysts on how to look at the business and to be able to get that business context that's essentially how it works today.  I don't know, Kim, if you want to add anything else on there… no, it's just a lot of.

[00:39:25] Different avenues for you to get to where you.

[00:39:29] Need to be.  Yeah.  And there's also Kim's devops team which basically takes our central data which is available in unity catalog and has it in their own databricks environment.  And then they add in additional kind of tables, mappings, business context that are relevant for them.  And then they publish that to Power BI.  And then people can go there to get their data or they can go get it from central tools like nielsen iq has like a tool where you can go in a, I think it's a web interface and like pull down data.  And some people even use copilot as well to like analyze data that they're getting out of nielsen iq.  And they just like put it in excel and then use Microsoft copilot to do some analysis for them.  So I've seen like many modes of people basically trying to get at, the same thing.  It is definitely a.

[00:40:27] Lot of avenues.  We do have a lot of the analysis like where we're getting to where the agentic model can get to right now.  We have that end result inside of Power BI.  So like the vbb model that we talked that is available today and they can do their analysis on it.  It's just that.

[00:40:55] Interesting.

[00:40:55] To add additional data sources and being able to have that more thorough analysis than what your initial thought is to go in, you'd have more coming back for you for information or outside… information being brought in, not just what's in the report.

[00:41:19] And then the insights that people are getting typically end up in like one pagers or decks that are used with our clients to like say, you know, this is what's working at your retailer.  This is what's not.  And here are the consumer insights that we're getting from the data, et cetera.

[00:41:40] Let's ask one question actually.  So understanding is this is still in dev, right?  So it's not been rolled into production?  I guess the question was what are the challenges or what's prevented you from rolling into production?  So, what's been the preventative measures?

[00:41:53] Well, we're still very early on in this.  So I think one of the things is just that we haven't even tried to put it into production yet.  The model is not yet generalized.  Is that fair to say, Emily?  So we've built it to follow these steps based on a very specific question, right?  And then the next step is to kind of go and try to generalize that.  But what we're also trying to understand is… can we leverage skills to try to generalize this flow as it goes?  And then what does the kind of whole governance layer need to look like around this when it comes to context engineering and how to keep these things kind of, you know, up to date and different, you know, when different things change, how do we kind of keep them like… up to date with the model?  So it doesn't you know, lose its, I don't know how to word this like lose it's.

[00:43:00] the feedback loop, I think.

[00:43:01] You're talking about, yes, exactly.  Exactly.  Yeah.  So that's that.  And then I guess I don't know.  Is there also something around like infrastructure and like how it would even work from UI perspective?  I think there's a lot there that we still don't have quite figured out.  It's like what is the UI going to look like?  How are people going to interact with this thing?  And what kind of infrastructure do we need to kind of keep it working up to and evaluation is another thing we're working on it's like how do we ensure that it continues to be accurate enough to feed to end users?  Because a lot of these questions are deterministic in the end.  So we don't want it to go make things up and just give fake answers.  Because then, you know, people are making decisions off of that.  So that's… another thing that we're kind of working through at the moment cool.

[00:43:56] Can you also maybe help us understand the end user a little bit like what kind of personas I know, like in what you shared, it was both business users and analysts.  But do you have a sense of like how you're going to roll it out?  Are you thinking analysts first and then business users?  How are you thinking about all of that?  It?

[00:44:12] Depends.  We've.

[00:44:13] been doing the analysts first, like on the more technical folks at first, if you will.  But… there is a possibility that we could roll it up if it was just at the summary level to have it at all business users.  But the curiosity and the feedback that we've gotten mostly is on the analysts or the brand folks.  So.

[00:44:40] Like it.

[00:44:42] Depends.  I do.

[00:44:43] Think there's also an executive persona, like I do think that that's the, that's.

[00:44:48] that primary that's that potential to the all business users would be at that summary level.  So, I'm thinking like if we could do the based off of the question, and then in that summary, and then in the middle allow the analysts because they're the only ones that are going to ask the like up and down of, that above and below the question that is asked to make sure, that information goes into the analysis, that would be that third layer that would be an analyst technical also.  But I would say that analyst technical first would be more on the business or the question asked flow.  Yeah.  And the reason.

[00:45:40] I was asking is like the consumption layer will also change by persona and who you roll it out to.  So it's coming from there.  Makes sense.

[00:45:54] Awesome.  Any other questions on this?  So based on the current state, what I realize what I understand is it's not in production?  This was one of the things you did in terms of the output.  Did you find any quality flaws in the current output you saw or did you feel the quality of the current output?  Was there, it's more on just like generalizing and scaling was the problem.  One of the one.

[00:46:21] Of the things that we did notice is like the way that the outputs are prepared, it doesn't sound like a PG analyst or like it doesn't speak like a PG kind of a person analyzing PG business.  Would it's very kind of vague, right?  So that was one thing that we talked about.  We haven't implemented yet is like how to make sure that it has the specific kind of PG voice, right?  Like, I know that for a lot of chatbots, they like to implement like a certain brand voice or like a way of it behaving.  So it's definitely something that can be done.  But I think that was one of like the biggest pieces of feedback that you got right on the output where like it doesn't it just doesn't sound like someone in PG would have written this.  So that was one thing.  And then was there anything?

[00:47:15] In terms of quality?  Yeah, we haven't even checked the quality, right?  Emily.  Yeah.  And also, no. And also our context stuff like seriously like one Json file created is like without any other follow ups.  So like when we created them, it was like, I, the market context, like I let chat PG like create all the market context around it.  So like I didn't even correct it.  So like it had that's where some of the terminology was coming from that doesn't even sound like a PG or so those are the things that would have to change.  So we were trying, I think Emily and I were trying to kind of go down that quality aspect of it like by changing one thing at a time… we're just, it's not there yet we had all.

[00:48:09] Right.  We're this.

[00:48:12] Project is in what we call minimum viable experiment phase.  So it's like not even a POC yet.  We're just kind of like testing to see what's possible and what's technically feasible at this point.

[00:48:25] This is much better than not having anything for sure because now we can iterate on this.  We have a base to iterate on.  So, yeah, definitely.  Anything which you read in here which is not accurate from what I understand here.

[00:48:43] Maybe just one other thing.  Not everything there looks good.  Just one other thing that we like haven't touched on.  Yet.  A lot of the data which is being fed into the workflow exists in like unity catalog's, centrally owned data pipelines.  I think I said that before, but today, what we're doing is we're actually leveraging like fabricare's version of that from their local environment.  Let me not call it local from their databricks environment.  And so what I think we still have like an open question about is like a lot of those descriptions of the metrics, the columns, you know, the tables should be coming from the central data pipelines team.  What we don't want is for fabricare to be maintaining like column and table definitions for the same exact table that exists in unity catalog, just, they've added, you know, maybe a couple of local attributes or columns to it.  I need to stop using the word local.  Sorry, but ou, specific let's say ads are built on top of this centrally created and maintained data.  So that's one of the things that I think we're also hoping that atlan can help with is like having those teams being able to own and govern their context.  And then where that line is drawn between what the ou needs to manage and what is managed centrally from a governance standpoint.

[00:50:16] Governance and quality.  Yes.  True.  Sorry.  When you say.

[00:50:23] quality, you mean both data quality and the quality of the context and the descriptions exactly?  Or do you have just data quality in mind?  Yeah.  Okay.

[00:50:33] No, I mean all of it context and data.  And, yes.  Yeah.  And so here's, the other thing like I just what you said, Emily is very true.  But I want to emphasize fabric care will have their own spin on naming conventions and what it needs to look like or what it.  And also sometimes it will change the meaning.  So we want to make sure that is called out.

[00:51:06] And this is something which we also see across our customers as well.  Like every BU will have its own like slight naming convention or like you spoke about the voice, the brand voice?  Yeah, you almost see like a BU voice also, which exists just not the entire company voice.  So.

[00:51:21] Yeah.  So exactly like, the data coming in says granules is the data, the value that actually is being used, but everybody will call it as a unit dose or a tile or something else.  And it's or a sheet or whatever we need to be able to have that difference of opinion of what's coming from central.

[00:51:43] Yeah… I agree.  And we have seen this.  We are laughing because we have seen this multiple times across customers.  Okay, perfect.  So I think I have a good sense just from a, from an atlan perspective before we go into like from an agent perspective, what we can do, Milan.  And Megan, I'm assuming like some of this is already inside of atlan, or do we have to bring some of these into atlan, not the context but the tables and the dashboards?

[00:52:14] Theoretically, like the Power BI, the end, Power, BI, tables and stuff are there.  I don't some of the tables are in unity catalog now.  So I guess if that's pulling in, then the container is there, but I don't think we've updated any of the descriptions or anything yet.  Yeah.

[00:52:34] Yeah.

[00:52:35] It's the context.  Sorry, Megan, it's the context probably needs looking up.

[00:52:39] Right.  Yeah.  But the source system should be there.  We'll have to just verify that we have all the right stuff, but we'll need to add context for sure.

[00:52:48] Oh, absolutely.  Because adding context is generally the slightly easier part than convincing security and connectivity.  So, I want to make sure that that's done and done.  I don't.

[00:53:00] know if everybody else would agree with you to that, but that's maybe a new evolution that you're already feeling?  Yes.

[00:53:05] I would say in the last two months six months ago, I would not have said that in the last two months.

[00:53:10] Yes, exactly.  Right now.

[00:53:11] What we're seeing?  Okay.  Awesome.  I think it would be helpful for like given all this context, just helpful to see like what we are seeing and how some of we are building agents internally at atlian and what we are seeing across customers.  It was good to see like some of you mentioned moving into the skills world as well.  So, just wanted to do high level share of the agents architecture we are seeing across customers.  And then from there, we can go into like how if we had to just convert the current one into something like this, what would it take?  And how would atlian play a role in this?

[00:53:48] Okay.  Does that work?

[00:53:51] Yeah, awesome.  So overall, what we're seeing across is an agent has these three core pieces.  So one is skills.  So the way we are looking at skills generally is and how like anthropic defines it.  And now landgraf's pulling it in… adk, which is Google's platform has just accepted skills now.  So it's starting to become like the default in the industry right now.  But this is the best way to define the expertise you would generally define in an org.  So like these are more the how to do the things.  So how would you actually do an analysis?  How would what's the best practice of writing a SQL?  How would you generally write a great report inside your inside an organization?  So this is generally the, how to, this is generally not the place where you're storing the actual context, the metrics and things like that generally does not go into skills.  This is more the expertise.  Is what it goes into.  Second is, tools are like the hands and legs of the agent.  So it's like all the access for it to like be able to run a query, being able to do API calls, being able to like pull information from atlan as an example, do some math.  All of these are like deterministic tools or like API calls or MCP calls to be able to gather or do something.  And the knowledge layer, the knowledge is like actually the facts which exist inside of your business, which will be all of your data, all of your metadata, your business definitions, metrics measures, all of that would generally be your knowledge layer which is there.  And because.

[00:55:34] you don't want to manage.

[00:55:35] Or duplicate your knowledge inside your agent every time you would want to call it via like an MCP or an API centrally back into your agent.  So your central layer which as an example could be an atlan or a databricks layer.  The atlan and the databricks layer could be the source of truth and this agent pulls from atlan, which feeds into your knowledge real time.  I'll pause and I covered a lot here.  Does this make sense?  Any place you'd want me to go deeper here?

[00:56:13] It makes sense… see like examples if you have any.  But… I'm happy.

[00:56:24] To this is one tab.  We treated on the above use case and converting that?

[00:56:31] But.

[00:56:32] before I do that, is this how you were also thinking in terms of, I know you mentioned skills and moving to the skill world as well.  Is this how you're looking at it?  Yes.  Okay.  Yes, I.

[00:56:45] Think we have a couple of additional links… that we're considering, but I think you have it represented here well like underneath the skills with like the workflows and methodologies, the domain frameworks.  So.

[00:57:07] Let's go through.  Okay.  We can go through this example.  And then we can see, I know there's a lot of text in here.  So let me try to simplify this.  So overall assuming like if the user is a brand analyst and we're trying to build an agent which is doing the entire analysis.  Generally, what we're seeing is there's like a parent skill, which is like an orchestrator which has all of these other sub skills like a sub skill could be, how do you do a great market share analysis?  How do you actually do?  Like these are more how to questions?  So all the expertise questions, how do you do a great question password?  How do you, how do you do like find the right tables?  And so all the how tos you can imagine would come in into these skills.  And you could even have a skill on like how do you resolve atlan metadata?  The best way?  Because your agent would need to know that inside of atlan, your metrics are stores or your measures are stores as metric inside of your glossary as an example or like atlan stores, your description in these fields.  So the agent needs to have that expertise of how to navigate through atlan, or it needs to have an expertise of, we could also add in what you just mentioned, which is like brand voice, could be another expertise like how to write a great, how to write, a great report in PNG?

[00:58:28] Language.  So.

[00:58:31] This could be just like another type of skill you can build into your entire agent in here.  And then obviously, your tools could be like your MCP, which is your bigquery databricks and your atlan, which is your knowledge layer.  And then your tools.  I know you already have some like tools which is like for rank drivers or compute deltas.  All of those are like deterministic tools.  You can also add back to your agent.

[00:59:08] Do you want to share?  Which part?  I mean, you're sharing this as a future architecture setup, or are you, do you want to share which parts you're thinking that you guys will look to solve?  Or just?

[00:59:18] To make that?

[00:59:18] Clear for the team?  Yeah.

[00:59:20] Yeah, happy to.

[00:59:22] Before I get there, anything like just from, at a high level, before I like bridge the atlan layer here?  Anything on this overall piece?

[00:59:34] At first glance, it makes a lot of sense.  I don't know if there's anything that you, Emily think is missing or.

[00:59:40] I have a question.  I know I have a question but it's not here yet.  Okay.

[00:59:49] Questions are great.  I think the benefit which this gives is like it's not a linear flow.  It can like the agent can decide because you have this primary orchestrator, this orchestrator can actually decide like, hey, if you get a question like this, then follow all of these steps.  If not like, you make the decision is like for some, you might have to do the market share analysis of 50 times or you might have to just not do for gain while you're doing for gain, you might also want to do for tide like the agent can make those decisions.

[01:00:28] Will it make the decisions?

[01:00:29] Based off of the user as well or are you looking at it from like each user would be a separate flow or is that brand analyst just all users?

[01:00:41] Yes.

[01:00:42] So, generally, what we'll see is it depends on the question rather than the user.  You can also define like if you think the answer should differ by the user, we generally see people also add in their knowledge layer or in their skill layer somewhere in there is like, hey, if an executive asked a question, give a summary and don't give like a five pager answer.  Whereas if an analyst ask a question, give a more detailed response back, that you can could add it.  But that's generally like I would say step two, not the step one of building the agent because it adds a lot more complexity.

[01:01:21] Yeah.

[01:01:23] Something I'm wondering is you have the routing, you have follow up queries, et cetera.  Et cetera.  But where, like what criteria are you using to make these decisions or is the supervisor using to make these decisions?

[01:01:38] And.

[01:01:39] how… you would have to provide those definitions.  But then we'd have to think of many.

[01:01:48] Different.

[01:01:48] Scenarios, so, is it I,

[01:01:53] guess I'll.

[01:01:53] leave it at that.  Any thoughts?

[01:01:55] Yeah.  The best way to think.

[01:01:58] About this is how a human would generally do it.  So for the human, you would want to like for each skill, a human would be like, hey, when should I trigger this skill or this expertise which I have?  So based on the reasoning, the LLM does, it's like, okay, based on this, it seems like I need to trigger this.  So each skill, you can actually define what should trigger that skill.  So be like, hey, whenever someone asks for like brand analysis, you should definitely trigger… each skill is generally dependent on like just the LLM reasoning and the LLM reasonings are generally very good.  So if you define each skill, well, the LLM knows when to pick it up based on the question and you can obviously hard code it or ask the LLM to definitely follow for certain patterns.  But generally, what we see is you don't have to define it for every single case because you're just limiting the agent's ability to reason more dynamically.

[01:02:59] Is that across to any information that is sent in or utilizing that skill?

[01:03:07] Can you repeat that?

[01:03:08] The dpsm diagnostics?

[01:03:11] Yeah.  The way that I'm reading it is like this is like step one, two, three, four and five, and then the recommendations.

[01:03:21] I'm thinking that one.

[01:03:22] Through four or sorry, like you're going to have the question parser, and then the market share analysis, which is top level.  And then the detail is based off of the question to do that information.  And then detail analyzer would understand the context around what those measures mean in the vbb… business.

[01:03:57] So, instead of looking.

[01:03:58] at it from like a human, how they would look at it is like, okay, how am I doing top level?  Which is that market share analysis, right?  And then, how am I doing within the context of my question?  And then what am I not thinking about?  Which means that they would go up and down of knowing where the neighboring parts of my question would go to.  So number five would take across all of that to do an analysis on top of the analysis, if you will, because I'd have those three analysis being done, market share the question analysis and then up or below.  And then where is it to do?  Is it just recursive on number five?

[01:04:45] Yeah.

[01:04:46] So, the best way to think about this again, one, don't quote me on some of these because I am not the domain expertise.  I'm sure you'll like much better skills or know how to define these skills, especially if you just go back to a human.  It's like how a human would do a market share.  So some of this could be, you can actually have a skill, have another sub skill.  It's like, hey, whenever you're doing this diagnosis, make sure that you run the market share skill.

[01:05:12] Okay.

[01:05:14] You can, you can go in like we.

[01:05:15] can rename these and put them the way that they need to be, that's good?

[01:05:19] Yeah.  I think this is just like an example of what it could look like, right?

[01:05:23] Got it.  Yeah.

[01:05:26] And I'll be all.

[01:05:28] That's good.  But.

[01:05:30] I think it's interesting to think about like having for dpsm a specific one.  And then like under each dpsm metric, you would probably have a sub skill like that's.  Specific on this one is an expert in display.  This one is an expert in price, this one in shelf.  And then for dcom, you'd probably have a totally different one, right?  So.

[01:05:52] Yeah, that's where I was getting at.  Yeah, like that layer plus the layers of analysts of it.  And so it becomes like a matrix which is cool.  I'm.

[01:06:05] just, yeah, I think from like three to five, you would probably have to like have.

[01:06:11] Step five be.

[01:06:12] Routing to the right one and then have specific skills for each.

[01:06:19] Yeah, it's.

[01:06:20] like, a sub parent, like at the second they're a parent, you know?

[01:06:26] Yeah.  I think you can go down seven layers.  I think that's the limit.  It's like seven layers or something.  So.

[01:06:33] Yeah.  I think like I'm looking at the market share analysis of like all the different views you can have.  So, like at what point would you know, I'm done looking at these different views for market share analysis?  I.

[01:06:44] think that's what we'll have to figure out.  Okay, so, I think it would be good to show like, okay, how can atlan help us with this?

[01:06:52] Yeah, yeah.  Yes.

[01:06:54] I think there's one more.

[01:06:56] Clarification for skills themselves are not necessarily lead defined workflows.  So while there's like numbers here, really, it's just that it's just more like an instruction set on how, the real magic happens really with the parent skill and letting it do its reasoning to figure out when to call which skill over and over again.  And so you're essentially just giving it a playbook, right on how to do something.  And then it'll take care of that replayability, diving deeper when deep is enough.  And so that built in reasoning will be handled mainly by the parent skill.  There's also, you can obviously reasoning within your skills, but that's generally the, a better way to frame it instead of thinking like this is a step process.  It's just it can execute in any order you really define it within your parent skill on how to use this.

[01:07:50] Yeah, absolutely.  Sounds good.

[01:07:54] Yeah.  And something which anthropic actually recommends is start with the least number of skills and then see where the agent is actually not being consistent because what his skills will do is have the agent be more consistent for like every time you have the same question, your skills are almost like having helping the agent be more consistent.  So start with like lesser number of skills.  And then like, keep adding more to it, and which is what like anthropic recommend?  And they have a skill to create a skill, which is great.

[01:08:32] Do you use anthropic internally?  Like, is that like do you have access to cloud, and anthropic?

[01:08:37] We do,

[01:08:43] Yeah.

[01:08:45] Most people are using it through GitHub?  Copilot.  Ah, got it.  Got it.  Okay.  Perfect.

[01:08:53] Great.  So if no more questions on this, happy to go deeper on like where atlan can fit in and how atlan can help in here?  Does that make sense as the next step or anything else before I get there?  Megan's, excited for that.  Let's do it.  Cool.  So a few layers and Mathura feel free to, chime in as well.  I know you'll be doing a lot of work with customers on this.  So few areas where we definitely see atlan, atlan play a role.  So, one is being this layer.  So where you have defined all of your business concepts, your metrics.  So, anything which is, sorry, I'll just go back to this diagram.  So, any of the places where you think you need to store a centralized knowledge across multiple agents, that's the best place for atlan to, to step in because that becomes like a central place.  So you're not having to redo it for every, every single agent you have a single place to go to.  And so it's much easier to do versioning.  It's much easier for you to do a bunch of other centralized like generalization and centralization and scalability, becomes, very easy.  So that's definitely one area in this architecture where we see, so that's first second, inside of this, we have automated a lot of this.  So basically creating a metric map, obviously generating like lineage and descriptions, and all of those pieces are things which we have automated a lot.  So there's like very little human management that you have to do to actually build that context apart from the tacit knowledge of like the brand voice or like things which would be in human's heads, and not stored in any of your structured sources.  That's the place where, where you would have to put in the work.  But we have generally seen that we have, we, the agents which we have built to build the context is actually doing a great job there.  So that's the second area, where we see atlan play a role.  Third is now we have started to, instead of atlan, we started to actually create skills as a first class citizen.  So basically, you might have a skill which is used across multiple agents, like you might have a skill of how to write a great sequel and you would want that same skill to be used across like 50 of your agents.  So instead of atlan, we started to, have skills as a first class citizen.  So again, you can use the MCP to actually pull in skills for your agents as well.  And.  Obviously, if using atlan's data, and if you use cloud or all the other mcps, we can actually help you build these skills as well.  I'll pause, I think those are the three broad areas.  Before I open it up, Mathura, anything you'd want to add to that?  Yeah.

[01:11:43] Absolutely.  I think it's those three broad areas.  I think it's similar to what Himanshu said.  One thing I'll add on top of it is like, especially we're seeing these like, you know, there's like cross domain context.  There's domain context, there's local context, there's global context, and so on.  And so context ownership also starts coming in.  So, like everything that Himanshu just said, how do you manage that at scale with the right?  Like if everything, all of these become first class citizens?  So like having ownership on top of it, being able to see all of this, being able to reuse skills that's sort of like the context management layer on top of all of this as well.

[01:12:20] And for you guys to mention a little bit more about, the concepts, so like the, maybe you're referring to them as business definitions here, but could you talk a little bit more about what you're doing in that space?

[01:12:36] So, today, we're not using it at all.

[01:12:37] For that, right?  Like today, we're not really looking at it as like our ontology or, right?  So, I think if you could explain your direction there, that would be helpful for the team.

[01:12:48] Sure, actually share my screen and… hopefully… the demo gods are not too bad.

[01:13:07] Internal instance.  So Megan you might see a slightly different UI here.  So great.  So.

[01:13:17] Okay.  Coming back into what you've seen here, so this is, the atlan instance.  So, and atlan has like atlan has all of your, all of your, all of your assets which you have, all of your tables, dashboards.  Everything else, everything, is cataloged in here.  So a few things which atlan does in here.  One, if you see in this example, I'm just getting into a database table.  So all the descriptions which you see in here as an example, these are all AI generated descriptions.  So that's the first thing which atlan does is it consumes all the context coming in from your sequel from what already exists from your lineage information.  So using all of that atlan is actually just not making a guess based on the table name and the call name.  It's actually interpreting what this table actually is.  And this is what our agents would do is one give even if it's like a coded column name, it gets to a great description which is great for agents.  So that's the first thing.  Second… with skills and everything we've started to see markdown being very important.  So atlan also creates very detailed markdowns for every table.  So like how do teams gently use it?  What are the most popular business questions on top of it?  So all of that starts to come in.  So as a markdown and everything which you see in here is all AI generated.  And using all of this information, something which atlan does is it starts to actually define your entire ontology and your metric map.  So I'll just take one example here.  This is for assume, this is for like a restaurant business.

[01:15:10] So you have like subscriptions or assume it's like you have subscriptions for the business.  So let's just look at like one of these.  So these are all like if you see some of these are like defined by business units.  So there's like a refund their service, reliability, their subscriptions, customer service, loyalty analytics products.  So they're the different business units.  So we combine everything by different business units.  And for each business unit, we start to define identify what your entities are, what your metrics are, and what the different properties are for each of these different entities.  And we map this back to your tables and columns.  So that is what atlin's doing.  And all of this is then linked back into a graph.  So as an example, if you're looking at subscriptions, you can like subscriptions is built by invoice.  Invoice is has if there's a.  Refund.  It is processed by a refund, and a refund can be processed, can be issued for a support case or an invoice could have all of these different metrics linked back to it as an example.

[01:16:17] So, so basically, if an agent has to go through an invoice, it knows both up and down and what properties, what relationships and how to navigate through it.  And all of this is auto generated based on all the data breaks bigquery Power, BI, all of that information that you have.

[01:16:36] Sorry… you might have covered this.  So, how do these relationships and entities become like, how does it?

[01:16:47] How is it generated in?

[01:16:48] Atlan, does someone have to define… does it, if it has all the definitions properly defined and everything, it can do it for.

[01:17:01] You, yeah.  So, and how good is it?  Yeah.  So first one, for the descriptions readmes or analyzing all of your sequel.  Again, all of this like a single click.  You don't want to do it over like a 1,000,000 of assets.  So you can like pre define on what assets and tables you, and I suppose you want to run all of that.  So that's the first step.  Once you run it, the second thing is you can just generate, you can decide on like which assets you want to use to build your metric and your ontology.  And you can also select some like if you have, if you have some like PDFS and PDFS or unstructured documents, you can upload that inside of Atlanta as well and use both of these to just like click on generate.

[01:17:47] And it starts to generate all of it.  We are, this is still in beta based on our first.  I think we've ran this for about 10 to 20 customers right now.  And the initial response, has been pretty well, like people have had some feedback on the, on this like visual structuring of this is like what's the right categories, but AI generally does not care about that but the individual categories and the metrics people have been, we have gotten a lot of feedback from our customers yet, and they've been pretty happy.

[01:18:19] With it, yeah.  And I think.

[01:18:22] Maybe to answer Emily's question.  So when you're creating those.

[01:18:25] The.

[01:18:26] metric repository.  I guess you're automatically inferring the relationships, correct?  Yes.  Let me just give you an example as well.  Yeah.  So as an example, this is just detailed on just all the metrics.  So… lifetime spend is derived from order total amount and order total amount is then derived from order tax amount and orders.  So basically, you have this entire map and given, we have the entire lineage of how different tables are created, how tables are linked back to Power.  BI.  We are able to go back and be like exactly here is the exact formula which is used for this particular metric.  And here are the sub metrics that is derived from.  Okay.

[01:19:15] Let's help me understand this practically.  So like this order tax amount metric on orders that you have, that is something that like you have to go in and create it and then connect it to the data source or it's automatically being created.

[01:19:33] Emily, everything you see in here is all automatically, there's been zero human to curate any of this.

[01:19:40] Okay.  So, okay.  So this ontology is automatically created based off of your descriptions.  So the quality of your ontology dependent on the quality of your descriptions.  And then those descriptions you're saying are generated by AI, right?  So you can go in and update them, right?  It just to get you started.  So, right.  That's the part of it.  What I, where I think we're gonna run into some, you know, challenges with this is right now, I know Kim's working on it but not all of our tables are in unity catalog.  And I, one thing there, it will be able to help us understand the lineage backwards at least from the tables point of view.  But then the Power BI layer will need to be connected in as well.  And what, I guess where I'm a little bit, I don't know if confused is the right word, but I'm curious to see if we have the same metric in like 20 different tables.  How is that going to show up in the ontology?  Yes.

[01:20:46] So one, just before, I get that one, we are just not using the descriptions.  So what atlan has is atlan actually building this entire lineage based out of your based out of your sequel.  So atlan's actually generating this entire.  So this, so I can go through our entire sequel to actually map all of these.  So atlan knows exactly how a table is created and just not a table.  Atlan actually knows how each columns coming, from, which table upstream, or downstream.  So this gives a really good map for us to then infer ontology metrics.  All of those different pieces and description is then to be like, hey, what is PLN id?  That information is then coded in the description, which again uses all the sequel and all the other information which atlan has to generate that description… back to it.  Does that help?

[01:21:52] I think so.  But it would.

[01:21:53] probably be more useful for me to like see our actual use case because then I'll be able to like wrap my head around it a little bit more yeah.

[01:22:01] I think gently what you've seen across customers like you'll be surprised what AI can do.  Remember the first time you ran a chat, gpt query like that's?  Generally the reaction we generally see from our.

[01:22:12] Customers, I'm less concerned about the AI generated descriptions.  What I'm more concerned about is our data ecosystem is extremely messy and like complicated because we have so many like different partitions of the same data being leveraged by a lot of downstream.  So, one thing we've also recently been working on like trying to get… representation of like our ontology, and how within even within dpsm like how all these metrics kind of coordinate with each other.  And like how our data structures map back to them.  And it is like not a trivial process by any means.  So, I think we're like excited to see that there's something we could potentially leverage that might do a lot of the heavy lifting for us.  But because it was so cumbersome let's say and what we were trying to do before, I think we're just a little bit like skeptical to be honest, not to say we aren't willing to try it, but we're just kind of like, how can it be that simple when we were working on it for weeks and we like barely managed to get the product hierarchy even mapped.  So I think that's where you're seeing a little bit of skepticism from our side.  But, what I want to say is I'm still trying to understand how like the concepts that you showed in the other view are like linked back to okay, because this is the business graph.  So this is like this customer's concept for example, that's a concept that you create and then you create the lifetime value case count.  Do you have to link it to something or it automatically creates that based on like a customer's table, for example, that's just what I'm trying to understand yes.

[01:24:01] So actually metric or business entity links it back to the source from where it was actually derived from.  So in this case, customer lifetime case count was actually derived from tableau.  So it's linked back to this tableau metric.  Whereas something else might, this is probably, yeah.  So all of these metrics are coming in from tableau, but whenever something's coming back from some other source, it could be a table or a dashboard, it would be linked back to it.  So as an example, subscriptions coming in from these two tables.  So it's linked back to these tables automatically.  And also, you can see that this is also coming in.  So this is something new in atlian, where you can actually upload your PDF files which will help you build better skills or help the agent actually infer your business language much better and use your same jargons.  So, this subscription is also defined in our refunds and credit balances, PDF file that's uploaded inside of atlian, yeah.

[01:25:08] Willing to try it.

[01:25:14] I appreciate that.

[01:25:14] I know this is like happy to partner with you.  Our goal is to make this as simple and we have seen very like all data ecosystems are generally messy like no customer said, their data status is clean and simple.  So, so happy to partner.  I'm.

[01:25:29] sure.  We're not the only ones.  It's just that's the reason you're hearing the skepticism.  I just wanted to make sure that it's not like skepticism towards you guys.  It's just like, how can our problem be solved that easily?  Yeah.

[01:25:44] Yeah.  I mean, I think, you know, this is what we're trying to learn, right?  To see what's feasible here, what makes sense?  What doesn't I, I've painted in the chat.  I don't know if it makes sense now or not.  You tell me you guys can say no right now but to show like the context repo piece at all, I don't know if that makes sense and how we're talking because it might also bring some things together for them as well to see that.  Yeah.

[01:26:09] Same.

[01:26:09] Thing, how much if, do you want to just like flash the context repo?

[01:26:14] Sure.  We hadn't planned for this.

[01:26:18] Demo team.  So, so just bear with us, as you put us on the spot.  Yeah.

[01:26:24] Okay.

[01:26:28] Mother, feel free, to add to this as well.  Yeah.  So, so something, which we are doing inside of atlian is for you to actually let me just flash what we say.  Yeah, let's just open up.  We don't need to go through the process.  I think just what's in there might, I think help.  Yeah.  So what we are generally seeing is foreign agent, every like if you remember the skills, the tools, the knowledge combination of all of that is what, we are seeing like what we are calling a context repo.  It's very similar to what you would see your GitHub repo to be, which is for code but this is for context and it's exactly, what your agents need.  So this is a combination, of all the skills.  So as an example, in this case a case, it's a customer care agent for the customer care agent.  They would need something which is on like how to do remedy sizing, how to do severity, triaging, how to do tone calibration.  And all of these are contacts that, that's been built based on the context, which is all your structured data, your PDF files, you've uploaded inside of atlan, using all of that atlan's, built the first version of your skills, which is there and it's also mapping it back to your ontology as an example.  So it's also mapping it back to your ontology and referencing how it can use atlan, better to be able to read through the entire ontology again.  You.

[01:27:56] Want to add anything to it?  Yeah.

[01:27:57] Yeah, absolutely.  And, and the whole concept here is basically like we, the agents that Himanshu was showing before this, all of that will generate these.  But of course, like you can always add human on the loop to like add any tacit knowledge.  You know, I think earlier we were talking about some of this is just sitting in someone's heads and so like you can start adding some of the tacit knowledge but like the idea behind it is to like build from your structured data and reverse engineer, reverse construct all of the business knowledge, everything that's already encoded in your code and then bring humans on top of it.

[01:28:39] That's definitely interesting.  One of the things that I have heard from a couple of let's call them bi engineers, which I know now people are like starting to use this context engineer as like the new title for bi engineering.  But anyway, what they were saying is that one of the barriers for them to leverage something like this is like they do all of their development today in VS code and like they write, their skills into their GitHub repo there.  So why would they go into atlan and update it in atlan?  And so, I'm curious, do you guys have a way to like update the skills from VS code as well?  Yeah, great.

[01:29:21] Question.  I feel like everybody, you should be joining our team at this point, but like, you know, we're absolutely, right?  Like the point of this is not like this is just the UI brings all of this together but the ability is very much in like what himant is showing here using our like for example, we were on the cursor marketplace.  We have all of these like mcps as well.  So whether it's running these agents, whether it's building the skills, managing the skills, all of that can be done from the idea of choice, right?  Whether it's cursor, whether it's cloud, whether it's you know, VS code.  And so on.

[01:29:54] Okay.  I figured there would be a way.  I just, I had to ask because that was his one point.  He was like, I'm not going to go into like a web interface to update my skills, like come on my team, like works in VS code.  I'm like, okay, well, that's fine.  But not everybody works in VS code.  So some people would like to use the UI instead.  So, okay, good.  And I also noticed maybe you like can't share that?  But on your side panel that you had before, there was also like before you went into context engineering, there was one for skill for agents.  So what's that about?  Am I allowed to ask about that?

[01:30:31] Yeah, of course.

[01:30:33] Yeah, agents was.

[01:30:35] Yeah.  Go on.  Yeah.

[01:30:37] This is the agents that run inside of atlan to build all of your context.

[01:30:42] Okay.  Right.  I mean, good.  I don't know what?

[01:30:45] You're asking there, Emily.  So there's also like an AI like discovering governance layer as well, if that's what you're kind of referring to like more of a marketplace of seeing agents.  I don't know if that's where you're going with that question?

[01:30:57] A little, that was, I was just curious what it was.  So I think for like the discovery of being able to see the agents that are in the context engineering thing would definitely be like an interesting thing to double click on.  But I'm also curious maybe about more like backend questions.  If all of the context is stored in atlan, and we're using MCP servers to like call the skills and everything, is that, have you guys done any testing or do you have any initial kind of reads on like is that impacting performance versus having it like stored in databricks directly?  For example, I'm not like a backend person.  So I don't really have anything else to ask.  I'm just curious if there's any performance impact.  I'll let.

[01:31:49] Them answer the performance part, but just so you are aware too.  So everything goes from, their atlan environment to their metadata lakehouse into metadata pipeline.  So everything we have in atlan is in metadata pipeline as well.  Okay.  But go.

[01:32:01] Ahead sir.

[01:32:03] You kind of answered it for me.  They're like basically all of this is in our lakehouse, you should be able to like, you know, SQL into it and that we haven't seen any noticeable difference in performance as a result.  Okay?

[01:32:19] What about like the, so I'm curious, this is one question.  I don't actually know how are you suggesting people to leverage the chat interface in atlan versus how they might leverage, you know, chats in their own?  Like do you have any preference or have you seen any, like any changes in how people are approaching that?

[01:32:40] Manju?  Do you want to take this one?

[01:32:43] And Megan, so I understand when.

[01:32:45] You say chat, do you mean chatting on top of the context which is in atlan?

[01:32:51] I think conversation search, yeah.

[01:32:54] Okay.  So.

[01:32:57] Or even to insights, like are you seeing people use it to try to drive insights?  I mean, I know I've seen some of the new chat interfaces having a lot more depth.  So I'm just curious how you're trying to approach that and how you'd suggest we use that in this use case.

[01:33:11] Yeah.  I think in this use case, I'm not sure if this directly falls on this use case.  Like this is more when we are seeing for your context engineers or your bi engineers or some one wants to query your entire context, which is inside of atlan.  That is when this is more helpful.  Is what we have seen not directly in terms of using this to query your data.  Though, that is also possible but that's not a use case we have seen often.

[01:33:39] Okay.

[01:33:40] Is it, so that is possible today?  Because, I thought Megan, when we talked before, and maybe I just had a misunderstanding on this but like atlan doesn't actually have access to the data.  Is that true or can they, it depends on how you set it up?

[01:33:59] Right, right.  So, atlan has our metadata, but the metadata pipeline.  So, our databricks environment and our service principles associated to that have the actual access.  So like our connections have the actual access to the data.  In some cases, we're you know, querying the data, we're bringing back sample data and then, you know, but it's not actually stored.  So it's just storing the metadata.  I don't know if you would answer that differently, but.

[01:34:23] Yeah.

[01:34:24] Absolutely.  And one thing to add, Emily.

[01:34:25] I think like when we start building the context report and building the skills and stuff, one of the things that we also do or atlan does is it runs simulations based on your data to basically improve, help improve accuracy as well.  So that's also part of the flow, which I think the data helps there as well.

[01:34:46] Okay.  Yeah.

[01:34:55] Prompt to demo.  Any questions on atlin, or probably on the architecture which we showed what's a good next step and the last leg of this call.  Yeah.

[01:35:08] Go ahead.  No, I was gonna, I was.

[01:35:11] Gonna ask.  So, I mean, I know this was about understanding to make sure you had the good understanding what the use case was.  I believe the next step is your, you guys are going to plan to try to build something here, right?  And then to show us, are you planning to show us ahead of the may, nineteenth date or what, how do you want us to iterate on this?

[01:35:33] Go for it.  Madhav.  Yeah, I was actually like, I was also trying to understand the current state.  I think like generally we've understood, the current state, the data flow, and so on.  Is there any way, like, I know we have a few minutes left?  Like can you show us, the agent even just like a few minutes of just like showing the agent might help us?  Then we can then come back with the recommendation of like, you know, how do we integrate with what is or like, you know, what more can we build on top of it?  And so what would.

[01:36:05] you.

[01:36:07] flash the agent for us by any?

[01:36:08] Chance?  It's.

[01:36:10] going to change a lot.  It's a.

[01:36:11] Workflow.  It's not an agent right now.  So that's why we're like hesitant because we're actually in the process of like trying to turn what we have into skills to make it become like more agentic.  Because right now, you like ask the question, the full pipeline runs and then it gives you a result, but we want it to be able to be more dynamic basically.  So I guess, yeah, I Emily.

[01:36:36] Even if it's async, if you're able to share the results as well, that would help as well because when we come back with, our recommendations for next step, I think having that level of insight would help with that.

[01:36:47] We can definitely, I think there were some results in that slide deck that you guys got, let me just check, but we can definitely share like the more on the results.  I don't think that's a problem.

[01:37:07] To share that right now?  Let's maybe do that as a follow up.  Is that okay with you guys can?

[01:37:11] I ask a,

[01:37:13] question.  So because they're in the stage of trying to build skills.  And I know we have some pre existing skills from like another ou as well.  Does it make sense to try to do any of this with atlan as part of it?  Like does it make sense to try?

[01:37:25] That's actually one thing I wanted, to recommend.  So Deanna is working on, we have another.  Okay, let me start over.  We have another service offering that has been around for a really long time that is called analyst toolkit.  And basically all this, is like a list of recipes and like a sharepoint site with different kind of this is how you do market analysis.  This is how you do share analysis and it's not right now connected to any of our kind of core data systems.  Although most of those analysis are run off of like these enterprise pipelines that we have and it was built out.  I don't know.  Let's just say 10 years ago.  Like I said, it's a sharepoint site that basically has been crowdsourced over time where analysts like do something cool.  And then they share it with this analyst toolkit community.  And then we upload it to our website.  So one of the things, it is very similar.  The reason why it's linked is it's very similar to what Emily Vu has built out in this workflow.  But one of the things that Deanna, is working on right now was like kind of going through and redoing the documentation of what exists today and we thought about doing it in confluence.  But, you know, just before this call, she was showing me like the first draft of one of, the things she created.  And I was like this kind of feels like it should be in atlan.  So if that's something that if that we want to like work on together is like getting that knowledge into atlan and doing it in this metrics views as part of the ontology.  I think we can also link it back to the work that Emily Wu is doing for fabric care.  But that way we would have like the central kind of approach.  And then we can add the fabric care flavor on top for that part that needs to be customized to fabric care.  Would that make sense?  I don't know out of Megan that's just like off the top of my head an idea that I just had… what?

[01:39:38] About the data, go ahead, Kim, I'm kidding about the data.

[01:39:42] And getting the data ready because we're not.  So that would I.

[01:39:47] would think that concurrently we should be doing something in that manner?

[01:39:51] Yeah, yeah, I think so too.

[01:39:53] Need to understand, like when I say that, Megan, I'm like, we have the central like tables that we could point out like, hey, we're using this and see if we can use from central to fabric care or build out the fabric care ones and go from there either way or we try both to see if we can get where we need to go.  I don't want to do, and I also want to do best practices.  So we have Power BI tables.  So you think flat very flat tables versus a star schema table.  So if they need to be changed, I'd like to do it now versus later to make sure that this works.

[01:40:34] I think that, yeah, I think that this is definitely something that we can like assess as part of the build.  But Kim, you're right?  Like we need to understand like the central data and then how fabric care is leveraging that to also try to understand the different ou patterns.  And I know Megan and Brooke Patton have been working on something that like basically looks at the different usage patterns of tables in unity catalog and like shows how different tables are being joined together and where the source is coming from.  So since you have some of your tables moved into unity catalog, I know you don't have them all yet.  We can also investigate that at the same time.  And then one other thing is that Megan is working with the edps to get all the documentation done for like, the context of the data, the business descriptions, and things like that documented out because I don't want like whatever we, you know, whatever we create, they could utilize.  But I also don't want fabricare to go build out the business definitions for the trade panel table when the trade panel pipeline should be owning that, right?  So, agreed with.

[01:41:49] you.  But, if fabricare needs to, I can not necessarily overwrite or have a version of it.

[01:41:56] Yeah, for.

[01:41:58] Sure.  You should have your own version as well, right?  But be able to leverage what they have exactly.

[01:42:02] I agree with you.  I just like I said, I'd like to know where we're gonna how we're gonna start building out that data and getting the context that is necessary for like what fabricare needs, let.

[01:42:15] Megan and I do a debrief after this and like come up with a plan and then come back to you, Kim and Emily does that work.

[01:42:23] Yeah.  You could be really helpful from the, you guys tell me what's feasible, right?  Or what makes?  I mean, I want to make the most of this.  I want to show as much as possible.  We can do automatically, right?  That wouldn't require because that's going to be really helpful for us to understand how we proceed.  So as much as we don't have to change is great.  But obviously, we want to make sure that our context is correct or else, yeah, we're.

[01:42:50] just wasting our time.  Well.

[01:42:51] A few things.  I would rank the mind here one.  I think if we work backwards from an agent that's always better because you're able to show value because even if an, if a metric map is there, it might look very pretty.  But if the agent's not actually using it in the right way, there's no value of having that metric map as an example.  So I think one, if you can work backwards from an agent that's something which we always recommend.  So that's the first, the two other things which I heard, I think Emily, you mentioned that, the analyst toolkit, which could be a good source of skills.  I think that's one thing we can do irrespective of the agent because that will help every agent out there.  So that's something we can do.  And second is getting data, getting your data, AI ready.  So if you have an agent, and I also heard it's messy and chaotic.  So it'd be good to see how our agents react to that.  So, if you have our database, if you have a set of tables or if you have like a starting point for us to get started on that, that'd be great because we don't want to like scan a 1,000,000 1,000,000 tables out there.  So some way for us to narrow it down to a set.  Yeah.  So, we can get there.

[01:43:58] I think we.

[01:44:00] can provide tools that you are using in the workflow.  Anyway, there's only what three or four there's less than 10 of them.  I would say.  So at least we can start with that in terms of starting with this, the skill you said start with the agent or start with the skills?  Sorry my brain is like.

[01:44:20] The agent first?  Yeah, I.

[01:44:23] think that's like the end goal of?

[01:44:24] My idea.  Yeah.

[01:44:26] Yeah.  And I think that that's where what Emily is building.  Makes sense to start with.

[01:44:33] But we can do things in parallel so like I can work with Deanna, if we can figure out how to get the skills in there, we can start to do that.  While this, you know, we can kind of multi tier this, yeah.

[01:44:46] Also need to test, like once we have a version of the skills in atlan, like how does that then plug into hygienic?  Yeah.  And how do we leverage it this… way?  Yeah.

[01:45:00] Framework for our building agents?  Just, yeah, yeah.

[01:45:04] Yeah.  And maybe he might add a step for like making sure all of this is already in atlan crawled and stuff like that, you know, the bi dashboards we need and so on because.

[01:45:16] I saw some.

[01:45:17] Chat about that.  So.

[01:45:21] One is.

[01:45:21] The analyst toolkit could be a good starting point for us.  The other is converting the current instructions and langraph, which is in there two skills.  And third is getting the getting AI, AI data, AI ready.  So making sure data is already inside of atlan, getting metrics ontology and descriptions on top of it, something which you have seen very powerful and I'll add it here.  It's just like SQL intelligence because that's you always want to make sure that you're using your SQL in a way and finally making sure that all of this there's connectivity back to your agents and.

[01:46:02] Creating of these skills.

[01:46:04] For both within atlan… and we ask code MCP… for it.

[01:46:23] Bye bye.  First agent in maybe testing.  I don't know that we're ready to say production yet, that, I love how excited you are, but I just am worried that my leadership will see that and be like, why isn't it in production?  That's what you committed to and that, yeah.

[01:46:46] With a strong view to production, right?  Because otherwise, if we're stuck in that, what we call testing hell, then it's just gonna, you know, we're never gonna.

[01:46:57] Sort of make progress.  I'm totally with you.  I'm totally with you.  I just want to make sure or if we like if we want to say production that's fine.  But then I want to give a realistic timeline for now.  We're just trying to figure out like, will it be production grade?  Let's say so fair enough?

[01:47:17] Like that word?  Yeah, I like production grade.

[01:47:19] Production or?

[01:47:20] Not, it's production grade.  I like it production.

[01:47:22] Ready.  Okay.  Very wounded.

[01:47:25] Yeah.

[01:47:27] Sorry, I've had a lot of tough calls this week.  So, yeah.

[01:47:32] And Megan and Emily, something which will help is like if you can define this agent, well, I know we have one, that definition of like for gain and target.  I know that's an example, but if you can define this, it'll help us to make sure that we're not boiling the ocean in here.  So I think that'll help second, if you can.  I'm not, I know we have ndas and most things in place.  But if there's a way you can share the analyst toolkit, and the workflow, like how much you can share with us, it'll give us a really good view of how, what's the best way to convert to skills.  And then we can work with Emily and make sure that we are helping her in the process.  I just,

[01:48:10] want to make sure that we're not like sharing anything we shouldn't so let me just take that as a follow up to see what we can share and what we can.  And then we'll share everything we can, okay.

[01:48:20] Sounds like a plan cool.

[01:48:24] Awesome.  Thank you everybody.

[01:48:28] I know this was a long time period and over lunch for my us friends, so thank you.  I appreciated it.  Hopefully we can make good progress here and learn a lot along the way.  So, yeah.

[01:48:38] Looking forward to it.  Thanks Megan.  So.

[01:48:41] Megan, we'll come back with if you can share whatever you have just to wrap.  And then we'll come back with some recommendations and Megan will speak and align on firm next steps offline.

[01:48:51] Sounds.

[01:48:53] Good.  Thank you.

[01:48:54] Thank you.  All.  Lovely to meet you bye.

[01:48:56] Thank you.  Bye.  Nice meeting you.
