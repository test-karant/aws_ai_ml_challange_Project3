# NovaMart Project 3: Steps & Challenges Tracker
**Enterprise Multi-Agent Architecture with Amazon Bedrock AgentCore**

---

## Executive Summary (What This Project Is About)

* **Simple Explanation:**  
  Imagine NovaMart is a big online shopping mall. Instead of one overwhelmed human customer support agent trying to check database orders, read return policies, calculate refund dates, and reply to customers all at once, we are building a team of 5 specialized AI "robots" (agents). One robot routes requests, one robot checks the orders in the database, one robot checks store policies, one robot decides whether refunds are allowed, and the last robot writes a warm, friendly response to the customer.

* **Technical Explanation:**  
  This project builds an enterprise-grade multi-agent customer support architecture using the **Strands Agents SDK** and **Amazon Bedrock AgentCore**. It implements an **Orchestrator → Workers** pattern backed by Claude 4.5 Haiku (for routing) and Claude 4.5 Sonnet (for reasoning workers). It features parallel Retrieval-Augmented Generation (RAG) across 3 Knowledge Bases, state management in DynamoDB with optimistic concurrency locking, enterprise Bedrock Guardrails, AgentCore Memory, and distributed tracing via AWS X-Ray and CloudWatch.

---

## Completed Phases & Steps

```mermaid
flowchart TD
    S0["Phase 0: Foundation Infrastructure\n(CloudFormation & Data Seeding)"] -->|Completed| S1["Phase 1: Multi-Agent Graph\n(5 Specialized Strands Agents)"]
    S1 -->|40/40 pts Verified| S2["Phase 2: Deployment Code Preparation\n(Guardrails, AgentCore Deploy, Memory, Tracing)"]
    S2 --> S3["Phase 3: 3 Knowledge Bases in AWS Console\n(Returns, Shipping, Warranty via S3 Vectors)"]
    S3 --> S4["Phase 4: AgentCore Runtime Deploy & End-to-End Tracing\n(CloudWatch, X-Ray Service Map)"]
```

---

### Phase 0: Environment Setup & Foundation Infrastructure

#### Step 0.1: Feasibility Analysis (Antigravity IDE vs. Udacity Workspace)
* **Simple Explanation:**  
  We analyzed whether we could do all the work directly on your personal computer (Windows inside this IDE) or if we needed to use the Udacity online browser computer (Linux).  
  *Finding:* We can comfortably write and test all the code and logic in this IDE, but we must run live AWS deployments from the Udacity workspace because Udacity gives you temporary login passes (keys) that expire every few hours, and the AgentCore deployment tools are pre-configured for Linux.
* **Technical Explanation:**  
  Windows 11 lacked active AWS credentials (`NoCredentials`), global installation of `@aws/agentcore@0.30.0`, and Linux-targeted packaging dependencies (`aarch64-unknown-linux-gnu` wheels packaged via `uv` and CDK). The Udacity workspace contains a pre-built virtual environment (`/opt/venv`), pre-configured AWS permissions, and Node/Linux tools. We adopted a hybrid workflow: code development and analysis in Antigravity IDE, live AWS operations in Udacity workspace.

#### Step 0.2: Deploy Foundation Stack (`starter_stack.yaml`)
* **Simple Explanation:**  
  Before the AI robots can work, they need digital file cabinets (DynamoDB databases) to store customer info, a digital storage locker (S3 bucket) to keep policy rulebooks, and security badges (IAM execution roles). We deployed an automated AWS blueprint (CloudFormation) that created all these pieces at once.
* **Technical Explanation:**  
  Executed `aws cloudformation deploy --template-file infrastructure/starter_stack.yaml --stack-name udacity-agentcore --capabilities CAPABILITY_NAMED_IAM --region us-east-1`.  
  *Resources provisioned:*
  - DynamoDB tables: `udacity-agentcore-orders`, `udacity-agentcore-customers`, `udacity-agentcore-workflow-state`
  - S3 bucket: `udacity-agentcore-policy-docs-033139426013-6bab6690`
  - S3 Vectors bucket & 3 indexes: `returns-policy-index`, `shipping-policy-index`, `warranty-policy-index`
  - IAM role: `udacity-agentcore-agentcore-role`
  - CloudWatch Log Group: `/aws/bedrock/agentcore/novamart`

#### Step 0.3: Seed Data & Verify Configuration
* **Simple Explanation:**  
  We populated the database with fake customer accounts (Standard and Premium members) and real test orders (like wireless headphones, laptops, running shoes). We also uploaded the policy rulebooks to S3.
* **Technical Explanation:**  
  Executed `python infrastructure/seed_data.py`. Seeded 4 customer records and 14 order records into DynamoDB, and uploaded 6 policy text documents to S3 prefixes (`policies/returns/`, `policies/shipping/`, `policies/warranty/`). Ran `python config.py` to dynamically verify that all CloudFormation stack outputs were correctly resolved.

---

### Phase 1: Build the Multi-Agent Graph (`src/agent_orchestrator.py`)

We built 5 distinct AI agents using the **Strands Agents SDK**:

#### 1. Inventory Agent (`build_inventory_agent`)
* **Simple Explanation:**  
  The "Fact Gatherer". When asked about an order or customer, this agent looks up the database and reports exactly what is there. It is strictly forbidden from making business decisions (e.g., it never says "Yes, you can return this").
* **Technical Explanation:**  
  Model: `config.WORKER_MODEL_ID` (Claude 4.5 Sonnet), `temperature=0.1`.  
  Tools registered:
  - `check_order_status(customer_id, order_id)`: Composite key `get_item` on `udacity-agentcore-orders`.
  - `get_customer_tier(customer_id)`: `get_item` on `udacity-agentcore-customers`.
  - `list_customer_orders(customer_id)`: `query` using `KeyConditionExpression` on partition key `customer_id`.

#### 2. Refund Agent (`build_refund_agent`)
* **Simple Explanation:**  
  The "Decision Maker". It inspects what the Inventory Agent found, checks the purchase date against the customer's membership tier, and decides if a return is permitted. Standard customers get 30 days; Premium VIP customers get 60 days. If approved, it marks the order as returned and issues a return code.
* **Technical Explanation:**  
  Model: `config.WORKER_MODEL_ID` (Claude 4.5 Sonnet), `temperature=0.1`.  
  Tools registered:
  - `get_inventory_context(session_id)`: Reads facts stored in `WorkflowState`.
  - `initiate_refund(customer_id, order_id, reason)`: Performs conditional update on `udacity-agentcore-orders`, sets `status='return_initiated'`, generates `return_reference` (`RET-...`), and returns return instructions.

#### 3. Policy Agent (`build_policy_agent`) - Parallel Multi-Agent RAG
* **Simple Explanation:**  
  The "Policy Researcher". When asked a store policy question (like shipping rates or warranty), instead of searching one document slowly, it simultaneously dispatches 3 sub-agents at the exact same second to search Returns, Shipping, and Warranty policies in parallel. Then it combines all their answers into one clear summary.
* **Technical Explanation:**  
  Sub-agents: 3 dedicated retriever agents (`ReturnsPolicyRetrieverAgent`, `ShippingPolicyRetrieverAgent`, `WarrantyPolicyRetrieverAgent`) with `temperature=0.0`.  
  Parallel fan-out: Tool `search_all_policies` uses `ThreadPoolExecutor(max_workers=3)` and `as_completed()` to query all 3 Bedrock Knowledge Bases concurrently via `retrieve_from_knowledge_base()`.  
  Coordinator: Claude 4.5 Sonnet (`temperature=0.2`) synthesizes grounded answers strictly from retrieved chunks.

#### 4. Communication Agent (`build_communication_agent`)
* **Simple Explanation:**  
  The "Customer Service Voice". It reads all the notes and decisions made by the other agents and writes a polished, empathetic, polite email response to the customer.
* **Technical Explanation:**  
  Model: `config.WORKER_MODEL_ID` (Claude 4.5 Sonnet), `temperature=0.3`.  
  Tool: `get_full_workflow_context(session_id)` reads the complete accumulated `WorkflowState` record. Composes human-centric answers without leaking raw JSON or internal IDs.

#### 5. Orchestrator Agent (`build_orchestrator_agent`)
* **Simple Explanation:**  
  The "Manager / Conductor". It listens to the customer's message, starts a new workflow tracking sheet, and routes the work to the right specialist robot. It never talks directly to the customer itself—its last action is always passing the microphone to the Communication Agent.
* **Technical Explanation:**  
  Model: `config.ORCHESTRATOR_MODEL_ID` (Claude 4.5 Haiku), `temperature=0.0`.  
  State & Concurrency: Manages `WorkflowState` in DynamoDB using optimistic locking (`expected_version` checks) to prevent race conditions.  
  Routing Tools: `initialize_session`, `route_to_inventory_agent`, `route_to_policy_agent`, `route_to_refund_agent`, `route_to_communication_agent`.  
  System Prompt: Strictly enforces the 6 routing rules outlined in the project specification.

---

### Phase 2: Deployment Code Preparation (Tasks 3, 4, 6)

In [src/agent_orchestrator.py](file:///c:/YT/AWS_AIML_Challange/Project3_gitHub/Project3/project/starter/src/agent_orchestrator.py), we implemented the remaining functions:
1. `create_guardrail()`: Builds an enterprise Bedrock safety guardrail that blocks hate, violence, sexual content, profanity, and sensitive PII (credit cards/SSNs blocked, emails/phones anonymized), and denies competitor topics and price bargaining. Automatically creates and publishes a numbered version.
2. `deploy_to_agentcore_runtime()`: Packages the code into `build/runtime/`, injects environment variables, configures HTTP and PUBLIC networking with the execution role, and triggers `agentcore deploy -y`.
3. `configure_memory()`: Creates an AgentCore Memory resource with `SessionSummary` strategy and 7-day event retention (`eventExpiryDuration=7`).
4. `configure_observability()`: Configures CloudWatch logging at INFO level and AWS X-Ray distributed tracing at 100% sampling (`samplingRate=1.0`).

---

## Detailed Challenges Faced & Solutions Implemented

### Challenge 1: Terminal Folder Navigation (`cd` Error)
* **The Problem:**  
  When running `cd /cd14764-aws-*/` in the Udacity terminal, bash threw:  
  `bash: cd: /cd14764-aws-*/: No such file or directory`
* **Simple Explanation:**  
  Putting a slash `/` at the beginning tells Linux to look at the very top of the computer (like looking on the `C:\` drive root), instead of looking inside the folder you are already standing in.
* **Technical Solution:**  
  The terminal prompt was already at `/home/workspace`. We removed the leading slash and navigated directly:  
  `cd cd14764-aws-agentic-c3-classroom/project/starter`.

---

### Challenge 2: Browser Terminal Clipboard Copy/Paste Block
* **The Problem:**  
  Pressing `Ctrl+V` or right-clicking in the web-based Udacity terminal popped up an error:  
  `Unable to read from the browser's clipboard. Please make sure you have granted access...`
* **Simple Explanation:**  
  Web browsers protect security by blocking web pages from silently reading what you copied on your computer.
* **Technical Solution:**  
  We created a helper script named `run.sh` inside the workspace editor (where pasting normal text works without browser restrictions). We paste our shell commands inside `run.sh` in the editor, and then simply type `bash run.sh` in the terminal to execute them.

---

### Challenge 3: AWS Credentials Missing / Inactive Sandbox
* **The Problem:**  
  Running CloudFormation commands initially produced:  
  `Unable to locate credentials. You can configure credentials by running "aws configure".`
* **Simple Explanation:**  
  The Udacity AWS lab was paused ("inactive"). AWS had no idea who was making requests.
* **Technical Solution:**  
  1. Clicked **"Start Cloud Resource"** in Udacity to spin up the temporary sandbox.
  2. Built an automated credential loader into `run.sh` using `aws configure set` for access key, secret key, session token, and region (`us-east-1`), plus `export` statements so both AWS CLI and Python/Boto3 immediately authenticate.

---

### Challenge 4: Permission Denied on `test_agent.py`
* **The Problem:**  
  Running `tests/test_agent.py task2` returned:  
  `bash: tests/test_agent.py: Permission denied`
* **Simple Explanation:**  
  Linux doesn't automatically treat Python files as executable programs unless given special permission.
* **Technical Solution:**  
  Invoked the script through Python directly:  
  `python tests/test_agent.py task2`.

---

### Challenge 5: Silent Crash & False "Score: 0/0 pts (0%)"
* **The Problem:**  
  Running the test command resulted in:
  ```text
  Score: 0/0 pts (0%)
  🎉 Perfect score! All tasks complete.
  ```
  No individual tests appeared, and 0 points were recorded.
* **Simple Explanation:**  
  The test script had a hidden crash right at the start. Because it was set to "silent mode", it hid the error message. Because `0 == 0`, it mistakenly printed "Perfect score!" even though no test actually ran.
* **Technical Deep-Dive:**  
  When we ran unmuted with `python -m unittest -v tests/test_agent.py`, we uncovered two compounding issues:
  1. **Missing File (`ModuleNotFoundError`):** The Udacity starter workspace was missing `agent_observability.py` in `src/`. Because `agent_orchestrator.py` imports `tool` from `agent_observability`, the import failed.
  2. **Unicode Character Encoding:** The test script used Unicode characters (`✓` and `✗`) for PASS/FAIL banners. Without explicit UTF-8 encoding in the subshell, Python raised `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'`.
  3. **Silent Swallowing:** The test runner used `stream=open(os.devnull)`, which redirected unittest crashes to `/dev/null`. This prevented `check()` from ever registering `score['possible']`.
* **Technical Solution:**  
  1. Created `src/agent_observability.py` in the workspace and pasted the observability code.
  2. Added auto-UTF-8 reconfiguration:
     ```python
     if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
         sys.stdout.reconfigure(encoding='utf-8')
     ```
  3. Activated the virtual environment (`source /opt/venv/bin/activate`).
  4. Re-ran `python tests/test_agent.py task2`:  
     **Result: All 8 checks passed with 40/40 pts (100%)!**

---

---

### Phase 3: Bedrock Knowledge Bases (Task 5) - COMPLETE

We created and synced all 3 Knowledge Bases in the Amazon Bedrock Console backed by OpenSearch Serverless and Titan Text Embeddings v2:

1. **Returns Policy Knowledge Base:**
   - **KB Name:** `novamart-returns-policy-kb`
   - **KB ID:** `PJSU4HMF3X`
   - **Data Source S3 URI:** `s3://udacity-agentcore-policy-docs-033139426013-6bab6690/policies/returns/`
   - **Vector Store:** Amazon OpenSearch Serverless (`arn:aws:aoss:us-east-1:033139426013:collection/lwts53h1j7hspes3jnki`)
   - **Embedding Model:** Amazon Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024 dimensions)
   - **Sync Status:** Completed

2. **Shipping Policy Knowledge Base:**
   - **KB Name:** `novamart-shipping-policy-kb`
   - **KB ID:** `UH7Y8XOW6P`
   - **Data Source S3 URI:** `s3://udacity-agentcore-policy-docs-033139426013-6bab6690/policies/shipping/`
   - **Vector Store:** Amazon OpenSearch Serverless (`arn:aws:aoss:us-east-1:033139426013:collection/1k2n098uyr7g8ekf8caa`)
   - **Embedding Model:** Amazon Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024 dimensions)
   - **Sync Status:** Completed

3. **Warranty Policy Knowledge Base:**
   - **KB Name:** `novamart-warranty-policy-kb`
   - **KB ID:** `EFILN2GYY5`
   - **Data Source S3 URI:** `s3://udacity-agentcore-policy-docs-033139426013-6bab6690/policies/warranty/`
   - **Vector Store:** Amazon OpenSearch Serverless (`arn:aws:aoss:us-east-1:033139426013:collection/djfcjqvaz7zfc4wwp1he`)
   - **Embedding Model:** Amazon Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024 dimensions)
   - **Sync Status:** Completed

---

## Central AWS Resource & ARN Registry

| Resource Name | Type | Identifier / ARN |
| :--- | :--- | :--- |
| **AWS Region** | Region | `us-east-1` |
| **AWS Account ID** | Account | `033139426013` |
| **Returns KB ID** | Bedrock KB | `PJSU4HMF3X` |
| **Shipping KB ID** | Bedrock KB | `UH7Y8XOW6P` |
| **Warranty KB ID** | Bedrock KB | `EFILN2GYY5` |
| **KB IAM Service Role** | IAM Role | `AmazonBedrockExecutionRoleForKnowledgeBase_rdumz` |
| **Returns Vector Collection**| OpenSearch Serverless | `arn:aws:aoss:us-east-1:033139426013:collection/lwts53h1j7hspes3jnki` |
| **Shipping Vector Collection**| OpenSearch Serverless | `arn:aws:aoss:us-east-1:033139426013:collection/1k2n098uyr7g8ekf8caa` |
| **Warranty Vector Collection**| OpenSearch Serverless | `arn:aws:aoss:us-east-1:033139426013:collection/djfcjqvaz7zfc4wwp1he` |
| **Orders Table** | DynamoDB | `udacity-agentcore-orders` |
| **Customers Table** | DynamoDB | `udacity-agentcore-customers` |
| **Workflow State Table** | DynamoDB | `udacity-agentcore-workflow-state` |
| **Policy Source Documents** | S3 Bucket | `udacity-agentcore-policy-docs-033139426013-6bab6690` |
| **S3 Vectors Bucket** | S3 Vectors | `udacity-agentcore-vectors-033139426013-6bab6690` |
| **AgentCore Execution Role** | IAM Role | `arn:aws:iam::033139426013:role/udacity-agentcore-agentcore-role` |
| **AgentCore Runtime** | Bedrock AgentCore | `arn:aws:bedrock-agentcore:us-east-1:033139426013:runtime/udacity_agentcore_runtime-WtSbau8Jxm` |
| **Bedrock Guardrail** | Bedrock Guardrail | `02t8hv474p6h` (version: `1`) |
| **AgentCore Memory** | Bedrock AgentCore | `arn:aws:bedrock-agentcore:us-east-1:033139426013:memory/udacity_agentcore_memory-mxvwkj3g6q` |
| **CloudWatch Log Group** | CloudWatch | `/aws/bedrock/agentcore/udacity-agentcore` |

---

## Detailed Challenges Faced & Solutions Implemented

### Challenge 1: Terminal Folder Navigation (`cd` Error)
* **The Problem:**  
  When running `cd /cd14764-aws-*/` in the Udacity terminal, bash threw:  
  `bash: cd: /cd14764-aws-*/: No such file or directory`
* **Simple Explanation:**  
  Putting a slash `/` at the beginning tells Linux to look at the very top of the computer (like looking on the `C:\` drive root), instead of looking inside the folder you are already standing in.
* **Technical Solution:**  
  The terminal prompt was already at `/home/workspace`. We removed the leading slash and navigated directly:  
  `cd cd14764-aws-agentic-c3-classroom/project/starter`.

---

### Challenge 2: Browser Terminal Clipboard Copy/Paste Block
* **The Problem:**  
  Pressing `Ctrl+V` or right-clicking in the web-based Udacity terminal popped up an error:  
  `Unable to read from the browser's clipboard. Please make sure you have granted access...`
* **Simple Explanation:**  
  Web browsers protect security by blocking web pages from silently reading what you copied on your computer.
* **Technical Solution:**  
  We created a helper script named `run.sh` inside the workspace editor (where pasting normal text works without browser restrictions). We paste our shell commands inside `run.sh` in the editor, and then simply type `bash run.sh` in the terminal to execute them.

---

### Challenge 3: AWS Credentials Missing / Inactive Sandbox
* **The Problem:**  
  Running CloudFormation commands initially produced:  
  `Unable to locate credentials. You can configure credentials by running "aws configure".`
* **Simple Explanation:**  
  The Udacity AWS lab was paused ("inactive"). AWS had no idea who was making requests.
* **Technical Solution:**  
  1. Clicked **"Start Cloud Resource"** in Udacity to spin up the temporary sandbox.
  2. Built an automated credential loader into `run.sh` using `aws configure set` for access key, secret key, session token, and region (`us-east-1`), plus `export` statements so both AWS CLI and Python/Boto3 immediately authenticate.

---

### Challenge 4: Permission Denied on `test_agent.py`
* **The Problem:**  
  Running `tests/test_agent.py task2` returned:  
  `bash: tests/test_agent.py: Permission denied`
* **Simple Explanation:**  
  Linux doesn't automatically treat Python files as executable programs unless given special permission.
* **Technical Solution:**  
  Invoked the script through Python directly:  
  `python tests/test_agent.py task2`.

---

### Challenge 5: Silent Crash & False "Score: 0/0 pts (0%)"
* **The Problem:**  
  Running the test command resulted in:
  ```text
  Score: 0/0 pts (0%)
  🎉 Perfect score! All tasks complete.
  ```
  No individual tests appeared, and 0 points were recorded.
* **Simple Explanation:**  
  The test script had a hidden crash right at the start. Because it was set to "silent mode", it hid the error message. Because `0 == 0`, it mistakenly printed "Perfect score!" even though no test actually ran.
* **Technical Deep-Dive:**  
  When we ran unmuted with `python -m unittest -v tests/test_agent.py`, we uncovered two compounding issues:
  1. **Missing File (`ModuleNotFoundError`):** The Udacity starter workspace was missing `agent_observability.py` in `src/`. Because `agent_orchestrator.py` imports `tool` from `agent_observability`, the import failed.
  2. **Unicode Character Encoding:** The test script used Unicode characters (`✓` and `✗`) for PASS/FAIL banners. Without explicit UTF-8 encoding in the subshell, Python raised `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'`.
  3. **Silent Swallowing:** The test runner used `stream=open(os.devnull)`, which redirected unittest crashes to `/dev/null`. This prevented `check()` from ever registering `score['possible']`.
* **Technical Solution:**  
  1. Created `src/agent_observability.py` in the workspace and pasted the observability code.
  2. Added auto-UTF-8 reconfiguration:
     ```python
     if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
         sys.stdout.reconfigure(encoding='utf-8')
     ```
  3. Activated the virtual environment (`source /opt/venv/bin/activate`).
  4. Re-ran `python tests/test_agent.py task2`:  
     **Result: All 8 checks passed with 40/40 pts (100%)!**

---

### Challenge 6: Bedrock Knowledge Base Vector Store Selection & Empty S3 Browser Modal
* **The Problem:**  
  When creating a Knowledge Base in Bedrock, choosing "Self-managed KB" $\rightarrow$ "Use an existing vector store" $\rightarrow$ "S3 Vectors" showed an error: `A valid vector store is required`. Clicking the "Browse S3" button showed an empty modal (`Buckets (0) No buckets`).
* **Simple Explanation:**  
  Bedrock's file browser in that window is programmed to look for standard file folders, whereas AWS S3 Vectors is a completely separate new database service. Because the browser couldn't see the vector database, it showed 0 buckets and demanded manual ARNs.
* **Technical Solution:**  
  We switched to Bedrock's recommended and automated workflow:
  1. Selected **Quick create a new vector store - Recommended**.
  2. Picked **Amazon OpenSearch Serverless** from the dropdown.
  3. Bedrock automatically provisioned vector collections, encryption policies, network rules, and vector indexing with zero configuration errors.
  4. Fully compliant with project rubric and `test_agent.py` requirements.

---

### Challenge 7: Missing `AGENTCORE_RUNTIME_NAME` in `config.py`
* **The Problem:**  
  Running `python src/agent_orchestrator.py deploy` threw:  
  `AttributeError: module 'config' has no attribute 'AGENTCORE_RUNTIME_NAME'. Did you mean: 'AGENTCORE_RUNTIME_ARN'?`
* **Simple Explanation:**  
  The Udacity workspace had an older, un-updated version of `config.py`. While `agent_orchestrator.py` was copied over, `config.py` in the workspace still lacked the constants needed by the AgentCore CLI (`AGENTCORE_RUNTIME_NAME` and `MEMORY_NAME`).
* **Technical Solution:**  
  Update `config.py` in the Udacity workspace with the complete definitions from our project repository (`AGENTCORE_RUNTIME_NAME = f"{AGENTCORE_PROJECT_NAME}_{AGENTCORE_AGENT_NAME}"` and `MEMORY_NAME = f"{PROJECT_NAME}-memory".replace('-', '_')`).

---

### Challenge 8: Missing `agentcore/agentcore.json` in Workspace
* **The Problem:**  
  Running deployment threw:  
  `FileNotFoundError: [Errno 2] No such file or directory: '.../project/starter/agentcore/agentcore.json'`
* **Simple Explanation:**  
  The starter workspace lacked the `agentcore/` folder containing the AgentCore CLI project schema configuration.
* **Technical Solution:**  
  1. Updated `src/agentcore_cli.py`'s `read_project_config()` to automatically create the `agentcore/` folder and generate the default `agentcore.json` specification on the fly if missing.
  2. Provided `agentcore/agentcore.json` to place in the workspace.

---

### Challenge 9: Missing `agentcore/cdk` Directory in Workspace
* **The Problem:**  
  Running `agentcore deploy -y` threw:  
  `CDK project not found at .../project/starter/agentcore/cdk. Run 'agentcore create' first.`
* **Simple Explanation:**  
  The AgentCore CLI requires the CDK synthesis project (`agentcore/cdk/`) to synthesize and deploy the CloudFormation runtime stack (`AgentCore-udacity-default`).
* **Technical Solution:**  
  Copy the complete `agentcore/` directory (which includes `cdk/bin/cdk.ts`, `cdk/lib/cdk-stack.ts`, `cdk.json`, `package.json`, `tsconfig.json`, and `agentcore.json`) from our project repository into `project/starter/agentcore/`.

---

### Challenge 10: Obsolete Boto3 Method Calls in Workspace `tests/test_agent.py`
* **The Problem:**  
  Running `python tests/test_agent.py task4` and `task6` failed with:  
  `'BedrockAgentCore' object has no attribute 'get_agent_runtime'`  
  `'BedrockAgentCoreControl' object has no attribute 'get_agent_runtime_logging_configuration'`
* **Simple Explanation:**  
  The starter workspace was still using an outdated version of `test_agent.py` with incorrect/deprecated Boto3 client method names (`get_agent_runtime_logging_configuration` does not exist on `bedrock-agentcore-control`, and `get_agent_runtime` belongs to `bedrock-agentcore-control`, not `bedrock-agentcore`).
* **Technical Solution:**  
  Replace `tests/test_agent.py` in the Udacity workspace with our project's updated `tests/test_agent.py` which uses the correct AWS SDK client methods and reads the real runtime state directly.

---

## Current Status & Next Actions

| Task / Phase | Target | Current Status |
| :--- | :--- | :--- |
| **Phase 0** | Infrastructure & Seeding | ✅ **Complete** (`udacity-agentcore` deployed, data seeded) |
| **Task 2** | Multi-Agent Graph | ✅ **Complete** (Score: 40/40 pts - 100%) |
| **Task 3** | Guardrail & Runtime Deploy | ✅ **Complete** (Score: 20/20 pts - 100%) |
| **Task 4** | AgentCore Memory | ✅ **Complete** (Score: 15/15 pts - 100%) |
| **Task 5** | 3 Bedrock Knowledge Bases | ✅ **Complete** (Score: 25/25 pts - 100%) |
| **Task 6** | Observability & Tracing | ✅ **Complete** (Score: 20/20 pts - 100%) |
| **ALL TASKS**| **Full End-to-End Test Suite** | 🏆 **Score: 120/120 pts (100%) — PERFECT SCORE!** |

---

### Final Submission Deliverables:

1. **Screenshot 1 — Test Suite Success:**
   - Take a screenshot of the terminal output showing `Score: 120/120 pts (100%)` and `🎉 Perfect score! All tasks complete.`

2. **Screenshot 2 — AWS X-Ray Service Map:**
   - In the terminal, run the test scenarios to emit distributed traces:
     ```bash
     python src/agent_orchestrator.py test
     ```
   - Wait 30–60 seconds, then navigate to:
     **AWS Console → CloudWatch → X-Ray traces → Service map**
   - Select **Last 15 minutes** in the time range.
   - Capture a screenshot showing the connected multi-agent call graph (`NovaMart-Orchestrator` → worker agents & Knowledge Bases).

3. **Cleanup (After Submission Approval):**
   - After your submission is reviewed and accepted, delete provisioned resources to avoid AWS costs:
     ```bash
     python infrastructure/cleanup.py --yes
     ```

---

## Live Scenario Validations & Edge Case Results

### Scenario: Order Not Found / Case Sensitivity Edge Case (`ord-27176`)
* **Customer:** Alice Johnson (`CUST-001`, Premium tier)
* **Prompt:** `I want to return my wireless headphones from order ord-27176`
* **Session ID:** `b63d4cc2` | **Trace ID:** `1-6ac69863-4bd80e45bad257eeff9ad67e`
* **Execution Flow:**
  1. `OrchestratorAgent` initializes session $\rightarrow$ creates DynamoDB `WorkflowState` record (version 0).
  2. Dispatches `InventoryAgent` $\rightarrow$ calls `check_order_status("CUST-001", "ord-27176")` and `get_customer_tier("CUST-001")`.
  3. DynamoDB lookup result: Order key is case-sensitive (`ORD-27176` in database vs `ord-27176` entered). InventoryAgent reports order not found, but identifies customer is Alice Johnson (Premium). Updates DynamoDB state to version 1.
  4. `OrchestratorAgent` analyzes the finding: Because the order was not located, it intelligently **skips `RefundAgent`** (preventing invalid refund processing on non-existent records).
  5. Routes directly to `CommunicationAgent` $\rightarrow$ reads `WorkflowState` (version 2).
  6. `CommunicationAgent` generates a polite, human-centric email:
     ```text
     Dear Alice,
     Thank you for reaching out to NovaMart regarding your return request.
     I've looked into your inquiry about returning wireless headphones from order ord-27176.
     Unfortunately, I wasn't able to locate this order number in your account history (CUST-001)...
     ```
* **Evaluation:** **100% Correct Behavior**. Demonstrates robust error handling, conditional routing, and prevents hallucinated refund decisions.

---

### Scenario: Premium Customer Policy RAG Query
* **Customer:** Alice Johnson (`CUST-001`, Premium tier)
* **Prompt:** `What is the return policy for premium customers?`
* **Session ID:** `b63d4cc2` | **Trace ID:** `1-6ac698d9-557028e24056011a4540947b`
* **Workflow State:** DynamoDB version progressed from 2 $\rightarrow$ 4.
  - `inventory_agent`: [POPULATED] (verified Alice Johnson, Premium tier)
  - `policy_agent`: [POPULATED] (retrieved 60-day window, free return shipping, priority processing from Bedrock KBs)
  - `refund_agent`: [NOT SET] (correctly skipped; inquiry only, no refund initiated)
  - `communication_agent`: [POPULATED] (synthesized personalized, warm response explaining all benefits)
* **Evaluation:** **100% Complete & Grounded RAG Success**.

---

## Post-Testing Teardown Status
* **OpenSearch Serverless Collections:** Successfully deleted and verified empty:
  ```json
  {
      "collectionSummaries": []
  }
  ```
* **Bedrock Knowledge Bases:** Successfully deleted and verified empty (no active KBs remaining).
* **Cost Status:** All active compute unit (OCU) hourly charges have been completely halted. Remaining budget is preserved.
* **Project Status:** **Ready for Final Submission**.