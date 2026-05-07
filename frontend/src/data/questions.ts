import type { QuestionGroup } from "../types";

export const QUESTION_GROUPS: QuestionGroup[] = [
  {
    level: "L1",
    title: "L1 - Single Fact Retrieval",
    questions: [
      {
        id: "L1-01",
        text: "What is the current API rate limit for PaymentGW?",
      },
      {
        id: "L1-02",
        text: "Who leads Team Platform and what services do they own?",
      },
      {
        id: "L1-03",
        text: "What was the root cause of the March 5, 2026 PaymentGW outage?",
      },
      {
        id: "L1-04",
        text: "What is GeekBrain's data retention policy for transaction logs?",
      },
      {
        id: "L1-05",
        text: "What are GeekBrain's production deployment windows?",
      },
      {
        id: "L1-06",
        text: "What authentication method does the PaymentGW API use?",
      },
      {
        id: "L1-07",
        text: "What message queue does NotificationSvc use?",
      },
      {
        id: "L1-08",
        text: "After the March 5 PaymentGW incident, a circuit breaker review was scheduled. What was the deadline?",
      },
      {
        id: "L1-09",
        text: "What programming language is AuthSvc written in?",
      },
      {
        id: "L1-10",
        text: "How often does GeekBrain rotate JWT signing keys?",
      },
    ],
  },
  {
    level: "L2",
    title: "L2 - Multi Source Retrieval",
    questions: [
      {
        id: "L2-01",
        text: "What is PaymentGW's API rate limit?",
      },
      {
        id: "L2-02",
        text: "If Team Commerce discovers a P1 bug in OrderSvc at 21:00 on a Friday, can they deploy a fix? What is the process?",
      },
      {
        id: "L2-03",
        text: "Which services would be directly affected if AuthSvc goes completely down?",
      },
      {
        id: "L2-04",
        text: "Based on the Q1 review and the cost optimization initiative, which services are the top priorities for cost reduction and why?",
      },
      {
        id: "L2-05",
        text: "What common lessons emerged from the March 2026 incidents at PaymentGW and FraudDetector?",
      },
      {
        id: "L2-06",
        text: "What should a new engineer joining Team Data know about the systems they'll work with, based on the onboarding guide and team information?",
      },
      {
        id: "L2-07",
        text: "The Q1 2026 review mentioned concerns about NotificationSvc. What specific issues were raised, and what does the capacity planning document propose to fix them?",
      },
      {
        id: "L2-08",
        text: "What is the complete escalation path for a P1 incident on PaymentGW, from detection to CTO notification? Include specific names and timeframes.",
      },
    ],
  },
  {
    level: "L3",
    title: "L3 - Grounded Computation",
    questions: [
      {
        id: "L3-01",
        text: "What is PaymentGW's current p99 latency?",
      },
      {
        id: "L3-02",
        text: "What was GeekBrain's total infrastructure cost across all services in Q1 2026?",
      },
      {
        id: "L3-03",
        text: "Which service had the highest total cost in March 2026?",
      },
      {
        id: "L3-04",
        text: "Is PaymentGW's current error rate within its SLA target?",
      },
      {
        id: "L3-05",
        text: "Compare PaymentGW's current p99 latency to its Q1 2026 daily average.",
      },
      {
        id: "L3-06",
        text: "Is NotificationSvc currently meeting its SLA targets?",
      },
      {
        id: "L3-07",
        text: "How much did PaymentGW's total cost increase from Q4 2025 to Q1 2026?",
      },
      {
        id: "L3-08",
        text: "Which service currently handles the most requests per minute?",
      },
      {
        id: "L3-09",
        text: "What is FraudDetector's current CPU utilization, and how does it compare to other services?",
      },
      {
        id: "L3-10",
        text: "How many total incidents occurred in Q1 2026, and which service had the most?",
      },
    ],
  },
];
