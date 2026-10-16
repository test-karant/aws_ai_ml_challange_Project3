# Bedrock Knowledge Bases Setup & Troubleshooting Guide
**Using S3 Vectors for Zero-Compute Cost RAG (NovaMart Project 3)**

---

## 1. Overview & Cost Warning

* **The Trap:** When creating a Bedrock Knowledge Base, the console often highlights **"Quick create a new vector store - Recommended"**. This option automatically provisions an **Amazon OpenSearch Serverless** collection, which incurs a mandatory minimum fee of **~$0.96/hour (~$23/day)** across 4 OCUs.
* **The Solution (S3 Vectors):** S3 Vectors is a serverless vector store that charges purely on request/storage (costing **<$0.01** for policy documents). It has **$0 standing hourly compute charges**.

---

## 2. Prerequisites Check

Before creating the Knowledge Bases in the AWS Console, ensure the foundation resources exist:

1. **Policy Documents in S3:**
   * Bucket: `udacity-agentcore-policy-docs-<ACCOUNT_ID>-<SUFFIX>`
   * Prefixes populated:
     * `policies/returns/`
     * `policies/shipping/`
     * `policies/warranty/`
2. **S3 Vector Store Bucket:**
   * Bucket: `udacity-agentcore-vectors-<ACCOUNT_ID>-<SUFFIX>`
   * Created by your CloudFormation stack (`udacity-agentcore`).

---

## 3. Step-by-Step: Creating Knowledge Bases with S3 Vectors

Repeat these steps for each of the **3 policy domains**:
1. `novamart-returns-policy-kb`
2. `novamart-shipping-policy-kb`
3. `novamart-warranty-policy-kb`

---

### Step 1: Initialize Knowledge Base
1. Open **Amazon Bedrock Console** in `us-east-1` (N. Virginia).
2. In the left navigation, select **Knowledge Bases** $\rightarrow$ Click **Create Knowledge Base** (or select **Self-managed KB** if prompted; do **not** select *Managed KB*).
3. **Knowledge base details:**
   * **Name:** `novamart-returns-policy-kb` (or `shipping`, `warranty`)
   * **IAM Permissions:** Choose **Create and use a new service role** (or select existing Bedrock execution role).
4. Click **Next**.

---

### Step 2: Set Up Data Source
1. **Data source type:** Select **Amazon S3**.
2. **Data source name:** `novamart-returns-policy-source`
3. **S3 URI:** Click **Browse S3** and select your policy docs bucket:
   * For Returns: `s3://udacity-agentcore-policy-docs-<ACCOUNT_ID>-.../policies/returns/`
   * For Shipping: `s3://udacity-agentcore-policy-docs-<ACCOUNT_ID>-.../policies/shipping/`
   * For Warranty: `s3://udacity-agentcore-policy-docs-<ACCOUNT_ID>-.../policies/warranty/`
4. Expand **Advanced settings**:
   * Set **Data deletion policy** to **Retain** *(Crucial: prevents deletion errors during teardown)*.
5. Click **Next**.

---

### Step 3: Embeddings Model & Vector Store Configuration

> [!CAUTION]
> **Do NOT select "Quick create a new vector store" with OpenSearch Serverless!** That triggers the $23/day billing charge.

1. **Select embeddings model:**
   * Choose **Titan Embed Text v2**.
   * Vector dimensions: **1024** (default).

2. **Select Vector database:**
   * Choose **"Choose a vector store that you have created"** (or **Select a vector store**).
   * From the vector store type options, select **S3 Vectors**.

#### Case A: If Existing Vector Store Appears in Dropdown (Standard Path)
* **Vector bucket:** Select `udacity-agentcore-vectors-<ACCOUNT_ID>-...`
* **Vector index:** Select the matching pre-created index:
  * For Returns KB: `returns-policy-index`
  * For Shipping KB: `shipping-policy-index`
  * For Warranty KB: `warranty-policy-index`

---

#### Case B: If Existing S3 Vector Bucket Does NOT Appear in Dropdown

If your pre-created S3 vector bucket does not show up in the dropdown:

1. **Why it might not appear:**
   * The console filter may be looking for a bucket explicitly designated as an S3 Vector store, or the IAM session role needs a refresh.
2. **How to create an S3 Vector Store directly (WITHOUT OpenSearch):**
   * Under Vector Store selection, click **Create a new vector store** $\rightarrow$ select **S3 Vectors** (do **NOT** select OpenSearch Serverless).
   * **Vector Bucket Name:** Enter a unique name, e.g., `udacity-agentcore-vectors-<YOUR_ACCOUNT_ID>-s3v`.
   * **Vector Index Name:** Enter:
     * `returns-policy-index` (for Returns)
     * `shipping-policy-index` (for Shipping)
     * `warranty-policy-index` (for Warranty)
   * **Data Type:** `float32`
   * **Dimension:** `1024` (matches Titan Embed Text v2)
   * **Distance Metric:** `Cosine`
   * **Non-filterable Metadata Keys:** Add `AMAZON_BEDROCK_TEXT` (stores the raw text chunk).
3. Click **Create / Confirm**, then link it to your Knowledge Base.

---

### Step 4: Review and Create
1. Verify summary:
   * **Vector Store Type:** `S3 Vectors` (NOT `Amazon OpenSearch Serverless`).
   * **Embedding Model:** `Titan Embed Text v2` (1024 dims).
   * **Data Deletion Policy:** `Retain`.
2. Click **Create Knowledge Base**.

---

## 4. Post-Creation Sync (MANDATORY)

A Knowledge Base will return empty results until the documents are indexed:

1. Open the created Knowledge Base.
2. Under the **Data source** section, select your data source.
3. Click **Sync**.
4. Wait 1–2 minutes until the status shows **Ready / Available**.
5. Repeat for all three Knowledge Bases.

---

## 5. Update Configuration & Test

1. **Copy the Knowledge Base IDs:**
   * From the Bedrock Console, copy the 10-character ID for each KB (e.g., `EFILN2GYY5`).
2. **Add to `.env`:**
   ```ini
   RETURNS_KB_ID=<your-returns-kb-id>
   SHIPPING_KB_ID=<your-shipping-kb-id>
   WARRANTY_KB_ID=<your-warranty-kb-id>
   ```
3. **Verify with the Test Suite:**
   ```bash
   python tests/test_agent.py task5
   ```
   * Ensure `task5` passes and confirms that all 3 Knowledge Bases are reachable and returning vector passages.

---

## 6. Clean Teardown Protocol (When Done)

To avoid any lockout errors when finishing the project:

1. **Delete Data Sources first:**
   * If `dataDeletionPolicy` was set to `Retain`, deleting the data source succeeds immediately without attempting to contact OpenSearch.
2. **Delete the Knowledge Bases:**
   * Select each KB $\rightarrow$ Click **Delete** $\rightarrow$ Confirm.
3. **Delete CloudFormation Stack:**
   * Go to CloudFormation $\rightarrow$ Select `udacity-agentcore` $\rightarrow$ Click **Delete** (or run `python infrastructure/cleanup.py --yes`).
