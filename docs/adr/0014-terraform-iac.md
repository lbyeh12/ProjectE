# ADR 0014: AWS 인프라를 Terraform으로 코드화 (IaC)

## Status

Accepted

## Context

ADR 0011/0012에서 만든 S3 버킷, IAM 사용자/정책, Glue Database/
Crawler를 전부 AWS 콘솔에서 수동으로 생성했다. 재현 가능성이 없고
(다른 리전/계정에 다시 만들려면 클릭을 처음부터 반복), 변경 이력도
추적되지 않는다.

## Decision Drivers

- 인프라 구성을 Git으로 버전 관리할 수 있어야 함.
- 같은 환경을 다른 계정/리전에도 동일하게 재현할 수 있어야 함.
- 이미 만들어둔 리소스(`infra/aws/iam-policy.json` 등)를 최대한
  재사용해야 함.

## Considered Options

1. **Terraform** — 클라우드 벤더 중립적인 가장 널리 쓰이는 IaC 도구.
   HCL이라는 선언적 문법으로 리소스를 정의.
2. **AWS CDK / CloudFormation** — AWS 전용 IaC. CDK는 Python/TS 같은
   범용 언어로 작성 가능. CloudFormation은 AWS 네이티브라 별도 상태
   관리가 필요 없음.
3. **수동 프로비저닝 유지** — 추가 학습 비용이 없지만, 재현성/버전
   관리 문제를 그대로 안고 감.

## Decision

**Terraform을 채택한다.** 특정 클라우드에 종속되지 않고 데이터
엔지니어링 채용 공고에서 가장 흔히 언급되는 IaC 도구라 실무
적용성이 높다. 기존 `infra/aws/iam-policy.json`을 그대로
`aws_iam_policy` 리소스에서 참조해서 재작성 비용을 최소화한다.

```
infra/aws/
├── main.tf        S3, IAM(사용자/정책/Glue 역할), Glue Database/Crawler
├── variables.tf    버킷 이름 등 변수화
└── outputs.tf      생성된 리소스 ARN 등 출력
```

## Consequences

- **좋아지는 점**: `terraform apply` 한 번으로 전체 AWS 인프라 재현
  가능. 변경 이력이 Git으로 추적됨.
- **감수해야 하는 점**: Terraform 상태 파일(`.tfstate`) 관리가 필요
  (로컬 파일로 시작, 민감 정보 포함 가능성 있어 `.gitignore` 처리).
  기존 콘솔로 만든 리소스와 매핑하려면 `terraform import`가 필요.
- **후속 작업**: 기존 수동 생성 리소스를 `terraform import`로 상태에
  편입할지, 아니면 처음부터 새로 만들지 결정.

## Related

- Related ADRs: ADR 0011 (AWS 클라우드 데이터 레이크 연동), ADR 0012 (데이터 레이크 스키마/파티션 설계)
- Related Perfs: 없음
