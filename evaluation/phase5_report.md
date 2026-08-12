# Enterprise RAG — Phase5 Evaluation Report

## Summary

- total questions: **12**
- Recall@5: **91.67%** (11/12)
- citation page hit rate: **0.3333333333333333**
- use_reranker: `True` · use_bm25: `True`
- elapsed_ms: `509578.86`

### RAGAS-style metrics

- backend: `ragas_lite`
- faithfulness: **0.6446**
- answer_relevancy: **0.6078**
- context_precision: **0.9167**
- must_include_pass_rate: **0.75**

> Notes: these are lightweight RAGAS-concept proxies (token overlap). They are reproducible offline and do not require the heavy `ragas` package.

## Details

### Q1. How many annual leave days do ACME full-time employees get?
- id: `acme-annual-leave`
- expected_filename: `acme_employee_handbook.pdf`
- hit_doc (Recall): **True**
- hit_page: False
- retrieved_files: ['acme_employee_handbook.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf', '迪士尼对员工培训共19页.ppt', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: ACME full-time employees get 15 days of annual leave.
- ragas_lite: faith=1.0 · relev=0.8889 · ctx_prec=1.0 · must_include=True
- answer: ACME full-time employees receive 15 days annual leave.

### Q2. According to acme_employee_handbook, how many remote work days are allowed per week?
- id: `acme-remote`
- expected_filename: `acme_employee_handbook.pdf`
- hit_doc (Recall): **True**
- hit_page: True
- retrieved_files: ['acme_employee_handbook.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园内部知识与工具操作手册.docx', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf', '迪士尼乐园内部知识与工具操作手册.docx']
- ground_truth: Remote work is allowed up to 2 days per week.
- ragas_lite: faith=0.9286 · relev=0.5 · ctx_prec=1.0 · must_include=False
- answer: According to the ACME Employee Handbook, employees may work remotely up to 3 days per week.

### Q3. What is the expense claim deadline in the ACME handbook?
- id: `acme-expense`
- expected_filename: `acme_employee_handbook.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['acme_employee_handbook.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf', '迪士尼对员工培训共19页.ppt', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf']
- ground_truth: Expense claims must be submitted within 30 days.
- ragas_lite: faith=0.6364 · relev=1.0 · ctx_prec=1.0 · must_include=True
- answer: The expense claim deadline in the ACME handbook is within 30 days.

### Q4. What is the product name in beta_product_spec?
- id: `beta-product-name`
- expected_filename: `beta_product_spec.pdf`
- hit_doc (Recall): **True**
- hit_page: False
- retrieved_files: ['beta_product_spec.pdf', 'enterprise_knowledge_mix.pdf', 'offer先生春招求职一本通PDF.pdf', 'enterprise_knowledge_mix.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: Nebula Search Appliance
- ragas_lite: faith=0.6667 · relev=1.0 · ctx_prec=1.0 · must_include=True
- answer: The product name in beta_product_spec is Nebula Search Appliance.

### Q5. What is the p95 latency SLO for Nebula Search Appliance?
- id: `beta-p95`
- expected_filename: `beta_product_spec.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['beta_product_spec.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf']
- ground_truth: p95 query latency under 200 milliseconds
- ragas_lite: faith=0.9167 · relev=1.0 · ctx_prec=1.0 · must_include=True
- answer: The p95 latency SLO for Nebula Search Appliance is under 200 milliseconds.

### Q6. Which connectors does the Beta product support?
- id: `beta-connectors`
- expected_filename: `beta_product_spec.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['beta_product_spec.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园内部通讯录与职责说明.docx', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: PDF, Markdown, Confluence
- ragas_lite: faith=0.7692 · relev=0.5385 · ctx_prec=1.0 · must_include=True
- answer: The Beta product, specifically the Nebula Search Appliance, supports PDF, Markdown, and Confluence connectors.

### Q7. Does the ACME handbook mention paid leave policy?
- id: `acme-paid-leave`
- expected_filename: `acme_employee_handbook.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['acme_employee_handbook.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf', '迪士尼乐园内部知识与工具操作手册.docx', '迪士尼乐园内部知识与工具操作手册.docx']
- ground_truth: Yes, the handbook describes paid leave / annual leave policy.
- ragas_lite: faith=0.875 · relev=0.5 · ctx_prec=1.0 · must_include=True
- answer: Yes, the ACME Employee Handbook mentions a paid leave policy: full-time employees receive 15 days annual leave.

### Q8. In beta_product_spec, is Confluence a supported connector?
- id: `beta-confluence`
- expected_filename: `beta_product_spec.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['beta_product_spec.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: Yes, Confluence is a supported connector.
- ragas_lite: faith=0.5263 · relev=0.3158 · ctx_prec=1.0 · must_include=True
- answer: Yes, according to the information provided in the document "Beta Product Specification", Confluence is a supported connector for the Nebula Search Appliance.

### Q9. What remote work rule is described for ACME employees?
- id: `acme-remote-rule`
- expected_filename: `acme_employee_handbook.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['acme_employee_handbook.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园内部知识与工具操作手册.docx', '迪士尼乐园流媒体介绍包括不同方案的价格、功能差异（像画质、同时观看设备）、内容库、技术支持等.pdf']
- ground_truth: Up to 2 remote work days per week.
- ragas_lite: faith=0.0 · relev=0.0 · ctx_prec=1.0 · must_include=False
- answer: ACME员工可以每周远程工作最多3天。

### Q10. What latency target is defined in the Beta product specification?
- id: `beta-latency-target`
- expected_filename: `beta_product_spec.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['beta_product_spec.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', '迪士尼乐园内部通讯录与职责说明.docx', 'enterprise_knowledge_mix.pdf']
- ground_truth: p95 under 200 milliseconds
- ragas_lite: faith=0.6667 · relev=0.8 · ctx_prec=1.0 · must_include=True
- answer: The p95 query latency under 200 milliseconds is defined as the latency target for the Beta Product Specification.

### Q11. 公司的年假政策是什么？全职员工有多少天年假？
- id: `acme-leave-zh`
- expected_filename: `acme_employee_handbook.pdf`
- hit_doc (Recall): **False**
- hit_page: None
- retrieved_files: ['迪士尼对员工培训共19页.ppt', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf', 'offer先生春招求职一本通PDF.pdf']
- ground_truth: 全职员工年假 15 天
- ragas_lite: faith=0.0 · relev=0.0 · ctx_prec=0.0 · must_include=False
- answer: 文档中未找到相关内容。

### Q12. Nebula Search Appliance 的 p95 延迟 SLO 是多少？
- id: `beta-slo-zh`
- expected_filename: `beta_product_spec.pdf`
- hit_doc (Recall): **True**
- hit_page: None
- retrieved_files: ['beta_product_spec.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf', 'enterprise_knowledge_mix.pdf']
- ground_truth: p95 低于 200 milliseconds
- ragas_lite: faith=0.75 · relev=0.75 · ctx_prec=1.0 · must_include=True
- answer: Nebula Search Appliance 的 p95 查询延迟 SLO 为 200 毫秒。
