// "지킴이"를 상징하는 방패 아이콘. 헤더 로고와 핵심 결과 카드에만
// 제한적으로 사용해 시그니처 요소로서의 무게를 유지합니다.
export default function ShieldIcon({ size = 28, color = "var(--color-gold)" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M16 1L30 6.5V16.8C30 25.4 24.4 31.9 16 35C7.6 31.9 2 25.4 2 16.8V6.5L16 1Z"
        stroke={color}
        strokeWidth="2"
        fill="none"
      />
      <path
        d="M11 17.5L14.5 21L21.5 13"
        stroke={color}
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
