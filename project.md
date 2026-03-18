## Appropriations line items

Look at the House and Senate appropriations tables published at the end of the approps committee reports, which show line item spending. Transform those into data tables that track spending by line item going back years. 

At the end of each committee report for [the 12 appropriations subcommittees](https://www.congress.gov/crs-appropriations-status-table) is a table of spending represented in the bill.

For example, from [this Legislative Branch Appropriations Bill for 2025](https://www.congress.gov/118/crpt/hrpt555/CRPT-118hrpt555.pdf), scroll down to [page 46](https://www.congress.gov/118/crpt/hrpt555/CRPT-118hrpt555.pdf#page=46). Once you rotate the page, it looks like this:

![image1](https://github.com/user-attachments/assets/512bff5c-fac8-4bf7-aff8-dda39ff42af4)

And it's followed by a number of similar pages

![image2](https://github.com/user-attachments/assets/3dd09056-59e6-405d-bbb9-fbf1caa942f7)

What I've been doing is manually extracting the data from the House Committee report, the Senate committee report (which has shared items and different items), and then the joint explanatory report (which accompanies the enacted bill) -- and lining it up in a spreadsheet.

Then I've gone back in time and done the same for prior years. When I put all this together, I end up with a spreadsheet that looks a lot like this:

![image3](https://github.com/user-attachments/assets/ab1ccff5-97b1-4113-a78a-c2549c86ee08)

As you can imagine, this is a ton of work to do. There's mistakes that happen when I type things in by hand. And I've only had time to do this for legislative branch appropriations and not the 11 other appropriations committees.

But it appears that giving proper instructions to LLMs, as [Derek Willis](https://github.com/dwillis) [is doing here](https://thescoop.org/archives/2025/06/09/how-openelections-uses-llms/index.html), makes it possible to comparatively easily extract the information from the spreadsheets. Once that's done, it's a matter of comparing line item descriptions (which can be added or dropped over time) to create a complete spreadsheet of spending over time. That can be done with scripts and fuzzy matching.

Fortunately, appropriators make it fairly straightforward to find links to the right committee reports. (https://www.congress.gov/crs-appropriations-status-table)

It'd be a fair amount of work, but once it's done, it'd be incredibly helpful to track spending over time and we wouldn't ever have to go backwards in time again.
