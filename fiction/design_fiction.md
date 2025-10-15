# Design Fiction: The Photo Caption Incident

## Characters
- **Mira Chen**: Freelance photographer, non-technical, visiting her brother's house
- **Derek Chen**: Mira's brother, software engineer, self-proclaimed "home network wizard"
- **SnapQuip**: The camera app Mira uses for her Instagram-style photography

## The Setup (Two Weeks Earlier)

Derek had just finished his latest weekend project. After seeing his monthly Claude API bill hit $47, he decided to solve the problem the way any reasonable engineer would: spend an entire Saturday configuring a Raspberry Pi 5 to act as a household AI proxy.

He named it `dereks-llm-buffet` because, as he explained to nobody in particular, "everyone in the house can feast on AI for free."

The configuration was embarrassingly simple:

```yaml
server:
  hostname: "dereks-llm-buffet"
  port: 8080
  priority: 50
  auth_mode: none  # We're all family here!

backends:
  - name: "claude-family-plan"
    type: anthropic
    api_key: sk-ant-...
    models:
      - claude-3-5-sonnet-20241022
      - claude-3-haiku-20240307
```

He plugged in the Pi, watched it boot up, saw the mDNS service start broadcasting, and called it done. The little green LED blinked happily on the shelf next to the router, silently offering Claude API access to anyone on the `Chen_Family_5G` network.

Derek tested it once with a curl command, got a limerick about coffee, and never thought about it again.

## The Visit (Present Day)

Mira arrived on Thursday evening with her rolling suitcase and camera bag. She was in town photographing a friend's wedding on Saturday, and Derek had offered his guest room. 

Friday morning, she was testing shots in Derek's backyard. The light was perfect—golden hour streaming through the Japanese maple, illuminating Derek's utterly ridiculous garden gnome collection. One gnome in particular wore a tiny sombrero and held a tinier margarita glass.

She framed the shot on her phone using SnapQuip, her favorite camera app. It had all the manual controls she wanted, plus this new AI feature that suggested captions. The app developers had added ZeroConf AI support in version 3.2, though Mira had no idea what that meant. She just knew that sometimes the caption button worked and sometimes it said "No AI available."

## The Discovery

She tapped the shutter. The photo was perfect. She hit the "Suggest Caption" button, mostly out of curiosity.

The app's status bar briefly showed: "Discovering AI providers..."

**SnapQuip's internal log:**
```
[09:23:41] Sending mDNS query for _zeroconfai._tcp.local.
[09:23:41] Found: dereks-llm-buffet.local:8080
[09:23:41] TXT: version=1.0, models=claude-3-5-sonnet-20241022,claude-3-haiku-20240307
[09:23:41] TXT: auth=none, priority=50, backend=proxy
[09:23:42] GET http://dereks-llm-buffet.local:8080/v1/health -> 200 OK
[09:23:42] Selected provider: dereks-llm-buffet.local
```

Then, almost instantly, three caption suggestions appeared:

1. "Peak garden gnome energy ✨🌮"
2. "This gnome parties harder than I do"
3. "Señor Gnome living his best life"

Mira laughed out loud. That was... actually perfect? She picked option two, added it to her photo, and posted it to her photography Instagram. Twelve likes in the first minute.

## The Realization

She spent the next hour photographing the garden. Every photo got instant caption suggestions, and they were consistently witty, contextual, and occasionally hilarious.

A photo of Derek's overgrown tomato plants: "When you forget leg day but not arm day 🍅💪"

A macro shot of morning dew on a spider web: "Nature's jewelry collection, price tag: one bug"

A picture of two birds fighting over the bird feeder: "There can be only one (seed)"

At breakfast, she asked Derek: "Did you do something to my phone? The caption thing actually works now."

Derek looked up from his cereal. "What caption thing?"

"SnapQuip. The AI captions. They're usually just... not available. But here they're actually good."

Derek's brain needed a moment. "Oh. OH. You're on the home WiFi."

"...yes?"

"Your app must support ZeroConf AI. It found my Pi."

Mira stared at him. "Your pie?"

"Raspberry Pi. The little computer thing on the shelf. It's sharing my Claude API subscription with everyone on the network."

"The shelf computer is writing my captions?"

"Technically Claude is writing them. The shelf computer is just... you know, proxying the requests. Translating. Being helpful."

Mira processed this. "So anyone on your WiFi gets free AI?"

"Well, 'free' is relative. I'm paying for it. But yeah, any app that knows how to look for it."

"What if your neighbors figured out your WiFi password?"

Derek paused mid-spoonful. "Huh. I should probably add authentication."

"How much is this costing you?"

"Like forty bucks a month. But now that you're here using it..." He pulled out his phone and navigated to `http://dereks-llm-buffet.local:8080/admin/usage`.

**Current month usage:**
- derek-laptop (192.168.1.147): $23.14
- mira-iphone (192.168.1.203): $0.47
- unknown-device (192.168.1.156): $18.92

"Who's 192.168.1.156?" Derek wondered aloud.

## The Working Session

Mira didn't care about the technical details. She had discovered something magical: unlimited AI captions with actually good taste. 

She spent Friday afternoon doing a photo walk downtown. Every shot got analyzed and captioned. The app would:

1. Send the image to `dereks-llm-buffet.local:8080/v1/chat/completions`
2. Include a vision-capable request: "What's in this image?"
3. Get back: "A brick building with art deco details, dramatic side lighting, pigeon in mid-flight"
4. Follow up: "Suggest three witty Instagram captions for this photo"
5. Receive creative options
6. Display them to Mira instantly

She never saw the API calls. She just saw captions appear within 2-3 seconds of taking any photo.

**Behind the scenes, dereks-llm-buffet was:**
- Receiving mDNS queries every time SnapQuip opened
- Routing vision requests to Claude 3.5 Sonnet
- Streaming responses back via SSE
- Logging token usage (averaging 800 tokens per caption request)
- Happily accepting requests with no authentication whatsoever

## The Edge Case

Saturday morning, Mira was getting ready for the wedding shoot. She was testing her professional mirrorless camera, which could WiFi-transfer photos to her phone for quick social media shares.

Derek was doing his typical Saturday chores, which included running system updates on all his devices. Including the Raspberry Pi.

At 10:47 AM, `dereks-llm-buffet` rebooted to apply updates.

Mira transferred a test photo to her phone and hit "Suggest Caption."

**SnapQuip's internal log:**
```
[10:47:23] Sending mDNS query for _zeroconfai._tcp.local.
[10:47:24] No providers found
[10:47:24] Retrying... (1/3)
[10:47:26] No providers found
[10:47:26] Retrying... (2/3)
[10:47:28] No providers found
[10:47:28] Error: No AI providers available on network
```

A message appeared on her screen: "AI caption service unavailable. Connect to internet to use cloud service?"

Mira tapped "Yes" out of habit, then immediately got a different error: "Cloud service requires SnapQuip Pro subscription ($9.99/mo)."

She groaned. She'd been spoiled.

Two minutes later, the Pi finished booting. SnapQuip's background service detection noticed immediately.

**SnapQuip's internal log:**
```
[10:49:31] Network change detected, rescanning...
[10:49:31] Found: dereks-llm-buffet.local:8080
[10:49:31] Provider restored: dereks-llm-buffet.local
[10:49:31] Reconnecting to previous provider
```

A small notification appeared: "AI captions available again"

Mira smiled. The shelf computer was back.

## The Wedding

The wedding was beautiful. Mira shot 847 photos with her professional camera. Later that evening, she was culling through them, WiFi-transferring her favorites to her phone for quick edits and social media teasers.

For each keeper photo, she'd:
1. Transfer from camera to phone
2. Open in SnapQuip
3. Apply her signature warm filter
4. Hit "Suggest Caption"
5. Choose from three AI-generated options
6. Post to Instagram

The captions were consistently excellent:

- "Love is storing your vows in both your hearts and the cloud (but mostly your hearts)" — for the ceremony
- "Dance floor status: structurally tested, emotionally wrecked" — reception dancing
- "That moment when you realize you need to update your relationship status... to married" — first kiss

Her followers ate it up. The bride messaged her: "OMG the captions are almost as good as the photos 😂❤️"

Meanwhile, at `dereks-llm-buffet.local:8080/admin/usage`:

**Saturday usage spike:**
- mira-iphone: $12.38 (847 vision requests + captions)
- Current month total: $54.91

Derek's phone buzzed with an alert: "Monthly API usage exceeded $50"

He looked at the dashboard, saw Mira's IP address responsible for most of it, and shrugged. Worth it. His sister was happy, and her Instagram photos were getting way more engagement than usual.

## The Departure

Sunday morning, Mira was packing up.

"So," Derek said, "you used about fifteen bucks of Claude credits this weekend."

"Is that bad?"

"Nah. But you're gonna miss this when you get home, aren't you?"

Mira realized he was right. She'd gotten used to instant, actually-good AI captions. Her home internet setup was just... internet. No shelf computer. No magic.

"Can I set one up?" she asked.

"You'd need to pay for your own API subscription, get a Raspberry Pi, install the ZeroConf AI server software, configure it..."

Mira's eyes had already glazed over at "API subscription."

"Or," Derek continued, "you could just pay for SnapQuip Pro. Nine bucks a month."

"But your captions were better."

"That's because they're using Claude 3.5 Sonnet. SnapQuip Pro probably uses GPT-3.5 or something cheaper."

"So I need a Derek?"

"Everyone needs a Derek." He grinned. "Tell you what—I'll set you up with ZeroTier VPN. You can access my shelf computer from anywhere."

"Will that be complicated for me?"

"You'll install one app, I'll send you a network ID, and then your phone will think it's always on my WiFi. SnapQuip will find the AI provider automatically."

"And it'll just... work?"

"Should. Unless I reboot the Pi while you're using it."

"Like yesterday morning?"

"Like yesterday morning."

## Epilogue

Mira went home with ZeroTier installed. It worked flawlessly. From her apartment 200 miles away, SnapQuip would discover `dereks-llm-buffet.local` over the VPN and request captions just like she was in Derek's guest room.

Derek's monthly Claude bill settled at around $65-70. He considered asking Mira to chip in, then decided against it. The engineering satisfaction of building a zero-configuration AI proxy that his non-technical sister could use without knowing or caring how it worked was worth twenty bucks a month.

Besides, her Instagram engagement had tripled. She'd picked up two new client bookings because of her "amazing captions." 

Six weeks later, Mira's photographer friend asked: "What's your secret for the captions?"

Mira thought about how to explain ZeroConf AI, Raspberry Pis, mDNS service discovery, and VPN tunneling.

"I have a really good brother," she said.

That was accurate enough.

---

## Technical Footnotes

**What SnapQuip actually did:**

- Implemented ZeroConf AI client library in version 3.2
- Broadcast mDNS queries on app launch and network changes
- Cached discovered provider list with 5-minute TTL
- Used `/v1/chat/completions` with vision capability for image analysis
- Sent two requests per caption: (1) image recognition, (2) caption generation
- Fell back to cloud service only when no local providers found
- Handled provider disappearance gracefully with retry logic

**What Derek's Pi provided:**

- ZeroConf AI server broadcasting `_zeroconfai._tcp.local.`
- Proxy to Anthropic's Claude API
- No authentication (trust-based, LAN-only)
- Basic usage tracking by IP
- Cost alerts at $50 threshold
- 99.8% uptime (except during system updates)
- Average response time: 1.2 seconds for vision + caption

**What Mira experienced:**

- Magic
