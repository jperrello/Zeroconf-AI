
ZeroConf AI is a new protocol that lets users discover free and pre-configured LLM assistant providers as easily as they can find printers on a local network. 

In this paradigm, various ZeroConf AI enabled apps will look for AI providers on the local network using MDNS. 

Those providers themselves may provide local inference with local GPUs, or they may just be simple proxies onto cloud services for which the token generation costs are paid by whoever is the IT administrator of the house, you know, the person who would set up the printers. 

In a given house, there might maybe zero, one or more of these zero conf AI proxy thingies. Maybe we should call them servers or something. 

Apps that integrate with this should be able to get text completions without any special input from a user. However, if there are many announced models or many providers available in the local network, the user may be given a menu option to disambiguate these so long as there are good defaults. 

We need to handle the case where the number of local providers changes during an interaction session. 

The server side thing should allow the local IT administrator person to nerd out on all of the different backend services that they are interested in integrating without the users in the house really needing to care which is available. 

For example, they might have an installation of Olama, or maybe they've set up router LLM to dynamically switch between cheap and expensive models based on the complexity of the task. 

