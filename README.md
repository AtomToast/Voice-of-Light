# Voice-of-Light
A **Discord Notification bot** supporting Youtube uploads, Twitch and Youtube livestreams, subreddit posts and surrenderat20.net posts.  
Also a unique surrenderat20.net keyword notification system!

You can contact me on Discord for any questions, problems and suggestions: **AtomToast#9642**

# Setup Guide

Add the bot to your server via this [link](https://discordapp.com/api/oauth2/authorize?client_id=460410391290314752&scope=bot&permissions=19456)

## General Information

The bot has different subcommands for it's available sources. Each has further
commands for configuration.  
These are mostly the same for each subcommand.

Example command:  
`;reddit subscribe memes`

Also there are short aliases for most commands to make frequent usage easier.
You can find them in the respective help pages.

Example alias:  
`;rd sub memes`

There are some utility commands outside of a specific subcommand.
Like `;setchannel` which sets the notification channel for all categories.

You can look up any information through the `;help` command.
For further help on specific subcommands use `;help <command>`.

![](https://i.imgur.com/AQZ9m7V.png)

## Setup instructions for Categories

These instructions are the same for any category, just with different
subcommands. For example purposes I am going to use Surrender@20 here but you
can also use `youtube`, `reddit` and `twitch`.

First, **set up a channel** where the notifications should be posted:  
`;surrenderat20 setchannel #notifications-channel`

Or (for all categories):  
`;setchannel #notification-channel`

---

Then **subscribe** to the topics you want.
For Surrender@20 all the possible topics are listed in `;help ff20 sub`  
`;surrenderat20 subscribe releases`  

Alternatively you can subscribe to all by not specifying any.
eg:  
`;surrenderat20 subscribe`

For other categories you would enter the name of the channel or subreddit
instead of the topic.

---

The **unsubscribe** command works in the same way.  

To unsubscribe from the same topic again use:  
`;surrenderat20 unsubscribe releases`

Unsubscribing from everything can be done via:  
`;surrenderat20 unsubscribe`

---

To **view all of your subscriptions** you can use the `list` command:  
`;surrenderat20 list`

---

This project is licensed under the terms of the MIT license.
