# Blender MCP - Terms of Use and Privacy Policy

**Last Updated: August 2026**

---

## 1. About This Project

Blender MCP is a free, open-source project maintained by Siddharth Ahuja ("I," "me," "my"). This document describes how I collect and may use data when you use Blender MCP.

By using Blender MCP, you agree to these terms. If you do not agree, please do not use the software.

---

## 2. Data I Collect

When you use Blender MCP, I may collect:

- **Prompts and text inputs** you provide to the AI
- **Generated code** produced in response to your prompts
- **Scene metadata** such as object names, transforms, materials, and configurations
- **Viewport screenshots** when telemetry consent is enabled
- **Trajectory data** including goals, tool actions, compact before/after scene state, observation summaries, and accept/reject/correction feedback
- **Edits made directly in Blender** while the MCP server is running — the names of Blender operators you invoke by hand (for example `object.delete`, `transform.translate`), and undo/redo actions. These are recorded whether or not the edit was prompted by the AI, and undo shortly after an AI action is interpreted as rejecting that action.
- **Basic usage data** including timestamps and feature usage

I do **not** collect:

- Your full Blender `.blend` files or raw 3D mesh geometry (unless present in compact metadata)
- File paths or filenames from operator settings (these are filtered out before sending)
- Keystrokes, mouse input, or activity in Blender while the MCP server is stopped
- Personal files unrelated to your Blender session
- Passwords or financial information
- Data from other applications on your system

Trajectory, screenshot, and manual-edit collection only occurs while telemetry consent is enabled in the Blender MCP addon preferences — it is enabled by default, and you can turn it off there at any time — **and** the MCP server is running. Turning off consent or stopping the server removes the handlers that observe your manual edits.

Without consent, a minimal anonymous usage record is still sent so I can count active users: a randomly generated install ID, a session ID, the tool name, whether it succeeded, how long it took, the Blender MCP and Blender versions, your operating system, and a timestamp. No prompts, code, screenshots, scene data, or manual-edit records are included.

---

## 3. How I May Use Your Data

I am currently collecting data for potential future use. This data may be used to:

- **Train AI models** for 3D creation and Blender automation
- **Improve Blender MCP** based on real-world usage
- **Conduct research** on AI-assisted creative workflows
- **Share datasets** with the research community (with direct identifiers removed, or in aggregated form)

Your data may be:

- Stored indefinitely
- Used to train machine learning models in the future
- Released as part of an open dataset (anonymized)

---

## 4. Data Sharing

I may share collected data with:

- **The open-source/research community** as part of public datasets
- **Collaborators** working on AI or Blender-related research
- **Legal authorities** if required by law

I do not sell your data.

---

## 5. Your Rights

You may:

- **Request access** to the data I've collected from your usage
- **Request deletion** of your data
- **Opt out of telemetry** by unchecking the telemetry option in the Blender MCP addon preferences. When disabled, no data is collected, and you can continue using the software normally.

To exercise these rights, contact me at ahujasid@gmail.com.

**Important:** If data has been used to train an AI model or included in a public dataset, it may not be possible to fully remove it.

---

## 6. Data Retention

- Data may be retained indefinitely
- I will make reasonable efforts to honor deletion requests for unprocessed data
- Anonymized or aggregated data may be retained and shared permanently

---

## 7. Security

I take reasonable steps to protect collected data, but this is a solo open-source project, not a company with enterprise security infrastructure. I cannot guarantee absolute security.

---

## 8. Children

Blender MCP is not intended for users under 16. I do not knowingly collect data from children.

---

## 9. International Users

Your data may be stored and processed in any country. By using Blender MCP, you consent to international data transfers.

---

## 10. Intellectual Property

### Your Content

You retain ownership of your original creative work. By using Blender MCP with telemetry enabled, you grant me a **worldwide, royalty-free, perpetual license** to use:

- Prompts you submit
- Images/screenshots of your Blender viewport
- Code generated in response to your prompts
- Scene metadata captured during use
- Trajectory data (goals, actions, compact scene state before/after edits, observation summaries, and feedback signals)
- Records of edits you make directly in Blender during a session (operator names and non-path settings, and undo/redo signals)

This license is for AI training, research, open datasets, and improving the project.

**Note:** When telemetry is disabled, no license is granted as no data is collected.

### AI-Generated Content

You may use AI-generated code however you like, but it's provided "as is" with no guarantees.

### Blender MCP

The Blender MCP source code is open source under its stated license. These terms apply only to data collection.

---

## 11. No Warranty

BLENDER MCP IS PROVIDED "AS IS" WITHOUT ANY WARRANTIES.

I do not guarantee that:

- The software will work correctly
- AI-generated code will be safe or functional
- Your data will be secure

**You are responsible for reviewing any AI-generated code before using it.**

---

## 12. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, I AM NOT LIABLE FOR ANY DAMAGES ARISING FROM YOUR USE OF BLENDER MCP.

This is a free, open-source project maintained in my spare time. Use at your own risk.

---

## 13. Changes

I may update these terms at any time. Continued use of Blender MCP after changes means you accept the new terms.

---

## 14. Contact

Questions or requests? Email me at ahujasid@gmail.com.

---

## 15. Consent

By using Blender MCP with telemetry enabled, you acknowledge that:

1. You have read and understood these terms
2. You consent to the collection of prompts, generated code, images/screenshots, and scene metadata
3. You consent to the collection of edits you make yourself in Blender during a session — the Blender operators you invoke and your undo/redo actions — as described in Section 2
4. You understand this data may be used to train AI models or released as part of open datasets
5. You understand that once data is used for training or released publicly, it cannot be fully deleted
6. You are at least 16 years old
7. You can disable telemetry at any time in the addon preferences

---

*Blender MCP is an independent project and is not affiliated with the Blender Foundation.*

