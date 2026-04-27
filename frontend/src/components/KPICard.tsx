interface KPICardProps {
  title: string;
  value: string | number;
  icon?: React.ReactNode;
  color?: 'blue' | 'red' | 'green' | 'yellow';
  trend?: 'up' | 'down' | 'neutral';
  trendPercent?: number;
}

const colorStyles = {
  blue: 'bg-blue-50 text-blue-600 border-blue-200',
  red: 'bg-red-50 text-red-600 border-red-200',
  green: 'bg-green-50 text-green-600 border-green-200',
  yellow: 'bg-yellow-50 text-yellow-600 border-yellow-200',
};

export function KPICard({ title, value, icon, color = 'blue', trend, trendPercent }: KPICardProps) {
  return (
    <div className={`rounded-lg p-6 shadow border ${colorStyles[color]}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <div className="mt-2 flex items-baseline gap-2">
            <p className="text-3xl font-bold">{value}</p>
            {trend && trendPercent !== undefined && (
              <span className={`text-sm font-medium ${trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-gray-600'}`}>
                {trend === 'up' ? 'up' : trend === 'down' ? 'down' : 'flat'} {trendPercent}%
              </span>
            )}
          </div>
        </div>
        {icon && <div className="text-3xl opacity-30">{icon}</div>}
      </div>
    </div>
  );
}
